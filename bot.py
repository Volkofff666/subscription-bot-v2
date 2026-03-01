"""
Главный файл Telegram бота с подписками + Stripe Webhook
"""

import asyncio
import logging
import os
import ssl
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from aiohttp import web

from admin import admin_router
from config import (
    ADMIN_IDS,
    BOT_TOKEN,
    CHANNEL_ID,
    MAX_CANCEL_REASON_LENGTH,
    SSL_CERT_PATH,
    SSL_KEY_PATH,
    SUBSCRIPTION_DAYS,
    SUPPORT_USER_ID,
    SUPPORT_USERNAME,
    WEBHOOK_HOST,
    WEBHOOK_PATH,
    WEBHOOK_PORT,
    validate_config,
)
from database import (
    cancel_subscription,
    create_subscription,
    get_subscription,
    get_user_stats,
    has_payment_attempt,
    init_db,
    is_subscription_active,
    mark_payment_attempt,
    save_cancellation_reason,
    save_user,
    update_subscription_period,
)
from keyboards import (
    back_to_status_keyboard,
    cancel_confirm_keyboard,
    main_keyboard_after_payment_attempt,
    main_keyboard_new_user,
    main_keyboard_subscribed,
    payment_keyboard,
    status_keyboard_active,
    subscription_offer_keyboard,
    support_keyboard,
)
from messages import format_message
from payments import PaymentFactory
from payments.stripe_pay import StripePaymentHandler
from subscription_tasks import subscription_enforcer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(admin_router)

subscription_task = None


class CancelSubscriptionForm(StatesGroup):
    waiting_for_reason = State()


# ==================== STRIPE WEBHOOK ====================


async def process_successful_payment(
    user_id: int, amount: float, currency: str, session_id: str, status: str = "succeeded"
):
    """Выдача или продление подписки после оплаты через Stripe"""
    try:
        logger.info(
            f"🔄 Обработка платежа для user {user_id}, amount={amount}, session={session_id}, status={status}"
        )

        if status == "renewed":
            # Auto-renewal: extend existing expiry, user is already in the channel
            sub = await get_subscription(user_id)
            if sub and sub["status"] == "active":
                new_expires = sub["expires_at"] + timedelta(days=SUBSCRIPTION_DAYS)
            else:
                new_expires = datetime.now() + timedelta(days=SUBSCRIPTION_DAYS)
            await update_subscription_period(user_id, new_expires)
            await bot.send_message(
                user_id,
                f"✅ <b>Подписка продлена!</b>\n\n"
                f"Доступ продлён ещё на <b>{SUBSCRIPTION_DAYS} дней</b>.\n"
                f"Ваша подписка активна до <b>{new_expires.strftime('%d.%m.%Y')}</b>.",
                parse_mode="HTML",
            )
            logger.info(f"🔄 Подписка продлена user {user_id} до {new_expires}")
        else:
            # First payment: create invite link and grant subscription
            invite = await bot.create_chat_invite_link(
                chat_id=int(CHANNEL_ID),
                member_limit=1,
                expire_date=timedelta(days=1),
                name=f"Sub_{user_id}",
            )
            invite_link = invite.invite_link

            await create_subscription(
                user_id=user_id,
                payment_provider="stripe",
                invite_link=invite_link,
                days=SUBSCRIPTION_DAYS,
                stripe_subscription_id=session_id,
            )

            await bot.send_message(
                user_id,
                f"✅ <b>Оплата прошла успешно!</b>\n\n"
                f"Доступ открыт на <b>{SUBSCRIPTION_DAYS} дней</b>.\n"
                f"Вот ваша ссылка:\n{invite_link}\n\n"
                f"⚠️ <i>Ссылка одноразовая и действует 24 часа.</i>",
                parse_mode="HTML",
            )
            logger.info(f"✅ Подписка выдана user {user_id}")

    except Exception as e:
        logger.error(f"❌ Ошибка выдачи подписки user {user_id}: {e}", exc_info=True)


async def stripe_webhook_handler(request: web.Request):
    """HTTP-обработчик для webhook от Stripe"""
    try:
        payload = await request.read()
        signature = request.headers.get("stripe-signature", "")

        if not StripePaymentHandler.verify_webhook_signature(payload, signature):
            logger.warning("⛔ Invalid Stripe webhook signature")
            return web.Response(status=403, text="Forbidden")

        result = StripePaymentHandler.parse_webhook(payload, signature)

        logger.info(f"🔍 Stripe webhook result: {result}")

        if result and result["status"] in ("succeeded", "renewed"):
            asyncio.create_task(
                process_successful_payment(
                    user_id=result["user_id"],
                    amount=result["amount"],
                    currency=result["currency"],
                    session_id=result["session_id"],
                    status=result["status"],
                )
            )
            return web.Response(text="OK")

        return web.Response(text="Ignored")
    except Exception as e:
        logger.error(f"❌ Stripe webhook error: {e}", exc_info=True)
        return web.Response(status=500, text="Error")


# ==================== ХЕНДЛЕРЫ БОТА ====================


@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    await save_user(user.id, user.username, user.first_name)

    is_active = await is_subscription_active(user.id)
    has_attempt = await has_payment_attempt(user.id)

    if is_active:
        keyboard = main_keyboard_subscribed()
    elif has_attempt:
        keyboard = main_keyboard_after_payment_attempt()
    else:
        keyboard = main_keyboard_new_user()

    await message.answer(
        format_message("welcome"), reply_markup=keyboard, parse_mode="HTML"
    )
    logger.info(f"👤 User {user.id} (@{user.username}) started bot")


@dp.callback_query(F.data == "subscribe")
async def show_subscription_offer(callback: CallbackQuery):
    await callback.message.edit_text(
        format_message("subscription_offer"),
        reply_markup=subscription_offer_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "pay_now")
async def process_payment(callback: CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username

    if await is_subscription_active(user_id):
        await callback.answer("✅ У вас уже есть активная подписка!", show_alert=True)
        return

    await mark_payment_attempt(user_id)
    payment_url = await PaymentFactory.create_payment(user_id, username)

    if not payment_url:
        try:
            await callback.message.edit_text(
                format_message("payment_error"),
                reply_markup=subscription_offer_keyboard(),
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            pass
        await callback.answer("❌ Ошибка создания платежа", show_alert=True)
        return

    try:
        await callback.message.edit_text(
            format_message("payment_invoice"),
            reply_markup=payment_keyboard(payment_url),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass
    await callback.answer("💳 Переходите к оплате!")
    logger.info(f"💳 Payment link for user {user_id}: {payment_url}")


@dp.callback_query(F.data == "status")
async def show_status(callback: CallbackQuery):
    user_id = callback.from_user.id
    sub = await get_subscription(user_id)

    if not sub or sub["status"] != "active":
        await callback.message.edit_text(
            format_message("no_subscription"),
            reply_markup=subscription_offer_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    days_left = (sub["expires_at"] - datetime.now()).days
    if days_left < 0:
        await callback.message.edit_text(
            format_message("no_subscription"),
            reply_markup=subscription_offer_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        format_message("status_active", days_left=days_left),
        reply_markup=status_keyboard_active(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "cancel_subscription")
async def ask_cancel_confirm(callback: CallbackQuery):
    await callback.message.edit_text(
        format_message("cancel_confirm"),
        reply_markup=cancel_confirm_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "cancel_confirm_yes")
async def ask_cancel_reason(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        format_message("cancel_reason_prompt"), reply_markup=None, parse_mode="HTML"
    )
    await state.set_state(CancelSubscriptionForm.waiting_for_reason)
    await callback.answer()


@dp.callback_query(F.data == "cancel_confirm_no")
async def cancel_no(callback: CallbackQuery):
    await callback.message.edit_text(
        format_message("cancel_thanks_for_staying"),
        reply_markup=main_keyboard_subscribed(),
        parse_mode="HTML",
    )
    await callback.answer("💙 Спасибо!")


@dp.message(CancelSubscriptionForm.waiting_for_reason)
async def process_cancel_reason(message: Message, state: FSMContext):
    reason = message.text[:MAX_CANCEL_REASON_LENGTH]
    user_id = message.from_user.id
    username = message.from_user.username

    sub = await get_subscription(user_id)
    await cancel_subscription(user_id)
    await save_cancellation_reason(
        user_id, username, reason, sub.get("stripe_subscription_id") if sub else None
    )

    if SUPPORT_USER_ID:
        try:
            await bot.send_message(
                SUPPORT_USER_ID,
                f"❌ Отмена подписки\n\n"
                f"👤 User: {user_id} (@{username})\n"
                f"💬 Причина: {reason}",
            )
        except Exception as e:
            logger.error(f"Failed to notify support: {e}")

    await message.answer(
        format_message("cancel_success_detailed"),
        reply_markup=main_keyboard_after_payment_attempt(),
        parse_mode="HTML",
    )
    await state.clear()
    logger.info(f"❌ User {user_id} cancelled subscription")


@dp.callback_query(F.data == "support")
async def show_support(callback: CallbackQuery):
    await callback.message.edit_text(
        format_message("support_menu"),
        reply_markup=support_keyboard(SUPPORT_USERNAME),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "renewal_decline")
async def renewal_decline(callback: CallbackQuery):
    await callback.message.edit_text(
        format_message("renewal_declined"),
        reply_markup=main_keyboard_after_payment_attempt(),
        parse_mode="HTML",
    )
    await callback.answer("Принято")


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    user_id = callback.from_user.id
    is_active = await is_subscription_active(user_id)
    has_attempt = await has_payment_attempt(user_id)

    if is_active:
        keyboard = main_keyboard_subscribed()
    elif has_attempt:
        keyboard = main_keyboard_after_payment_attempt()
    else:
        keyboard = main_keyboard_new_user()

    await callback.message.edit_text(
        format_message("welcome"), reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    stats = await get_user_stats()
    provider = PaymentFactory.get_provider_name()

    await message.answer(f"📊 СТАТИСТИКА БОТА\n\n{stats}\n\n💳 Провайдер: {provider}")


# ==================== ЗАПУСК ====================


async def on_startup():
    logger.info("🚀 Инициализация бота...")
    try:
        validate_config()
        logger.info("✅ Конфигурация валидна")
    except ValueError as e:
        logger.error(f"❌ Ошибка конфигурации: {e}")
        raise

    await init_db()
    provider = PaymentFactory.get_provider_name()
    logger.info(f"💳 Платежный провайдер: {provider}")

    # Проверяем доступ к каналу
    try:
        chat = await bot.get_chat(int(CHANNEL_ID))
        logger.info(f"✅ Канал найден: {chat.title or chat.id} (id={CHANNEL_ID})")
    except Exception as e:
        logger.error(
            f"❌ Не удалось получить доступ к каналу CHANNEL_ID={CHANNEL_ID}: {e}\n"
            "   Проверьте:\n"
            "   1. CHANNEL_ID в .env — для приватных каналов формат: -100XXXXXXXXXX\n"
            "   2. Бот добавлен в канал как администратор с правом приглашать участников"
        )

    logger.info("✅ Бот успешно запущен!")

    global subscription_task
    subscription_task = asyncio.create_task(subscription_enforcer(bot))


async def on_shutdown():
    logger.info("🛑 Остановка бота...")
    global subscription_task
    if subscription_task:
        subscription_task.cancel()
    await bot.session.close()


async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # SSL
    ssl_context = None
    if os.path.exists(SSL_CERT_PATH) and os.path.exists(SSL_KEY_PATH):
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(SSL_CERT_PATH, SSL_KEY_PATH)
        logger.info("🔒 SSL сертификаты загружены")
    else:
        logger.warning("⚠️ SSL сертификаты не найдены")

    # Webhook сервер
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, stripe_webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, WEBHOOK_HOST, WEBHOOK_PORT, ssl_context=ssl_context)
    await site.start()

    protocol = "https" if ssl_context else "http"
    logger.info(
        "🌍 Webhook server: %s://%s:%s%s",
        protocol,
        WEBHOOK_HOST,
        WEBHOOK_PORT,
        WEBHOOK_PATH,
    )

    # Бот
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⚠️ Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
