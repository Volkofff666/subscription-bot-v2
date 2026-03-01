"""
Админ-панель для управления ботом
"""

import logging
from html import escape
from datetime import datetime
from typing import Dict, List

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import ADMIN_IDS, CHANNEL_ID, SUBSCRIPTION_DAYS
from database import (
    cancel_subscription,
    create_subscription,
    get_all_users,
    get_db,
    get_subscription,
    get_user_stats,
    is_subscription_active,
)
from keyboards import renewal_offer_keyboard
from messages import format_message
from payments import PaymentFactory
from subscription_tasks import backup_database

logger = logging.getLogger(__name__)
admin_router = Router()

# ==================== STATES ====================


class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_user_search = State()
    waiting_for_manual_sub_user = State()
    waiting_for_manual_sub_days = State()
    waiting_for_legacy_usernames = State()


# ==================== PAGINATION ====================


class UsersPaginator:
    """Пагинация для списка пользователей"""

    def __init__(self, users: List[Dict], page: int = 0, per_page: int = 10):
        self.users = users
        self.page = page
        self.per_page = per_page
        self.total_pages = (len(users) + per_page - 1) // per_page

    def get_page_users(self) -> List[Dict]:
        """Получить пользователей текущей страницы"""
        start = self.page * self.per_page
        end = start + self.per_page
        return self.users[start:end]

    def get_keyboard(self) -> InlineKeyboardMarkup:
        """Создать клавиатуру со списком пользователей"""
        keyboard = []

        # Кнопки с пользователями
        for user in self.get_page_users():
            user_id = user["user_id"]
            username = user.get("username", "Без username")
            first_name = user.get("first_name", "Неизвестно")

            display_name = (
                f"@{username}"
                if username and username != "Без username"
                else first_name
            )
            button_text = f"👤 {display_name} (ID: {user_id})"

            keyboard.append(
                [
                    InlineKeyboardButton(
                        text=button_text[:64],  # Telegram limit
                        callback_data=f"user_profile_{user_id}",
                    )
                ]
            )

        # Навигация
        nav_buttons = []

        if self.page > 0:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="⬅️ Назад", callback_data=f"users_page_{self.page - 1}"
                )
            )

        nav_buttons.append(
            InlineKeyboardButton(
                text=f"📄 {self.page + 1}/{self.total_pages}",
                callback_data="users_page_current",
            )
        )

        if self.page < self.total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="Вперед ➡️", callback_data=f"users_page_{self.page + 1}"
                )
            )

        if nav_buttons:
            keyboard.append(nav_buttons)

        # Кнопка "Назад в админку"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text="🔙 Назад в админку", callback_data="admin_panel"
                )
            ]
        )

        return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ==================== KEYBOARDS ====================


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users_list")],
            [InlineKeyboardButton(text="🔍 Найти пользователя", callback_data="admin_search")],
            [InlineKeyboardButton(text="💎 Выдать подписку", callback_data="admin_give_sub")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="🔔 Уведомить старую базу", callback_data="admin_legacy_notify")],
            [InlineKeyboardButton(text="📋 Причины отмен", callback_data="admin_cancellations")],
            [InlineKeyboardButton(text="📥 Экспорт пользователей", callback_data="admin_export")],
            [InlineKeyboardButton(text="💾 Бекап базы данных", callback_data="admin_backup")],
            [InlineKeyboardButton(text="🧪 Диагностика и тест оплаты", callback_data="admin_diagnostics")],
        ]
    )


def back_to_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 Назад в админку", callback_data="admin_panel"
                )
            ]
        ]
    )


def confirm_broadcast_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Отправить", callback_data="broadcast_confirm"
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel")],
        ]
    )


def user_profile_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура профиля пользователя"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💎 Выдать подписку", callback_data=f"give_sub_{user_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отозвать подписку", callback_data=f"revoke_sub_{user_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Детали подписки", callback_data=f"sub_info_{user_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Написать пользователю",
                    callback_data=f"message_user_{user_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 К списку", callback_data="admin_users_list"
                )
            ],
            [InlineKeyboardButton(text="🏠 В админку", callback_data="admin_panel")],
        ]
    )


def _format_join_date(value) -> str:
    """Формат даты регистрации для админки."""
    if not value:
        return "Неизвестно"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return str(value)


def _format_subscription_info(sub: Dict) -> str:
    """Единый формат блока подписки."""
    if not sub:
        return "Статус: нет подписки"

    status = sub.get("status")
    expires_at = sub.get("expires_at")
    provider = sub.get("payment_provider", "не указан")

    if status == "active":
        if not expires_at:
            return "Статус: активна\nДата окончания: не указана"
        days_left = (expires_at - datetime.now()).days
        if days_left >= 0:
            return (
                "Статус: активна\n"
                f"Осталось дней: {days_left}\n"
                f"Провайдер: {provider}\n"
                f"Действует до: {expires_at.strftime('%d.%m.%Y %H:%M')}"
            )
        return f"Статус: истекла\nДата окончания: {expires_at.strftime('%d.%m.%Y %H:%M')}"

    if status == "cancelled":
        if expires_at:
            return (
                "Статус: отменена\n"
                f"Доступ до: {expires_at.strftime('%d.%m.%Y %H:%M')}"
            )
        return "Статус: отменена"

    if status == "expired":
        if expires_at:
            return f"Статус: истекла\nДата окончания: {expires_at.strftime('%d.%m.%Y %H:%M')}"
        return "Статус: истекла"

    return f"Статус: {status or 'неизвестен'}"


def _build_profile_text(
    user_id: int,
    first_name: str,
    username: str,
    join_date,
    has_payment: bool,
    cancellations_count: int,
    sub: Dict,
) -> str:
    """Единый рендер профиля пользователя для админки."""
    first_name_text = escape(first_name or "не указано")
    username_text = f"@{escape(username)}" if username else "не указан"
    payment_attempts = "Да" if has_payment else "Нет"
    subscription_info = escape(_format_subscription_info(sub))

    return (
        "<b>ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        f"<b>ID:</b> <code>{user_id}</code>\n"
        f"<b>Имя:</b> {first_name_text}\n"
        f"<b>Username:</b> {username_text}\n"
        f"<b>Регистрация:</b> {_format_join_date(join_date)}\n"
        f"<b>Попытки оплаты:</b> {payment_attempts}\n"
        f"<b>Отмен подписок:</b> {cancellations_count}\n\n"
        f"<b>Подписка:</b>\n{subscription_info}"
    )


async def _create_invite_link(bot: Bot, label: str) -> str:
    """
    Создаёт одноразовую ссылку-приглашение в канал.
    При ошибке бросает RuntimeError с понятным описанием.
    """
    from datetime import timedelta
    try:
        invite = await bot.create_chat_invite_link(
            chat_id=int(CHANNEL_ID),
            member_limit=1,
            expire_date=timedelta(days=1),
            name=label,
        )
        return invite.invite_link
    except Exception as e:
        err = str(e)
        if "chat not found" in err.lower():
            raise RuntimeError(
                f"❌ Канал не найден (CHANNEL_ID={CHANNEL_ID}).\n\n"
                "Проверьте:\n"
                "• CHANNEL_ID в .env — для приватных каналов формат: <code>-100XXXXXXXXXX</code>\n"
                "• Бот добавлен в канал как <b>администратор</b> с правом приглашать участников"
            ) from e
        if "not enough rights" in err.lower() or "forbidden" in err.lower():
            raise RuntimeError(
                "❌ Недостаточно прав.\n\n"
                "Дайте боту права <b>администратора</b> в канале с разрешением «Приглашать пользователей»."
            ) from e
        raise RuntimeError(f"❌ Ошибка создания ссылки: {e}") from e


def _parse_usernames(raw: str) -> List[str]:
    tokens = raw.replace(",", " ").replace(";", " ").split()
    usernames = []
    seen = set()
    for token in tokens:
        username = token.strip().lstrip("@").lower()
        if not username or username in seen:
            continue
        seen.add(username)
        usernames.append(username)
    return usernames


# ==================== HANDLERS ====================


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Открыть админ-панель"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к админ-панели")
        return

    await message.answer(
        "🔧 <b>АДМИН-ПАНЕЛЬ</b>\n\nВыберите действие:",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML",
    )
    logger.info(f"👤 Admin {message.from_user.id} opened panel")


@admin_router.callback_query(F.data == "admin_panel")
async def show_admin_panel(callback: CallbackQuery, state: FSMContext):
    """Вернуться в главное меню админки"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "🔧 <b>АДМИН-ПАНЕЛЬ</b>\n\nВыберите действие:",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ==================== СПИСОК ПОЛЬЗОВАТЕЛЕЙ ====================


@admin_router.callback_query(F.data == "admin_users_list")
async def show_users_list(callback: CallbackQuery):
    """Показать список пользователей (страница 1)"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    await show_users_page(callback, page=0)


@admin_router.callback_query(F.data.startswith("users_page_"))
async def navigate_users_page(callback: CallbackQuery):
    """Навигация по страницам пользователей"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    page_data = callback.data.split("_")[-1]

    if page_data == "current":
        await callback.answer()
        return

    page = int(page_data)
    await show_users_page(callback, page)


async def show_users_page(callback: CallbackQuery, page: int):
    """Отобразить страницу со списком пользователей"""
    try:
        # Получаем пользователей с дополнительной информацией
        async with get_db() as db:
            async with db.execute(
                """
                SELECT u.user_id, u.username, u.first_name, u.join_date,
                       s.status, s.expires_at
                FROM users u
                LEFT JOIN subscriptions s ON u.user_id = s.user_id
                ORDER BY u.join_date DESC
                """
            ) as cursor:
                rows = await cursor.fetchall()
                users = [
                    {
                        "user_id": row[0],
                        "username": row[1],
                        "first_name": row[2],
                        "join_date": row[3],
                        "sub_status": row[4],
                        "expires_at": row[5],
                    }
                    for row in rows
                ]

        if not users:
            await callback.message.edit_text(
                "👥 Пользователей пока нет", reply_markup=back_to_admin_keyboard()
            )
            await callback.answer()
            return

        paginator = UsersPaginator(users, page=page, per_page=10)

        # Формируем текст с информацией
        text = (
            f"👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
            f"📊 Всего: {len(users)}\n"
            f"📄 Страница {page + 1} из {paginator.total_pages}\n\n"
            f"Выберите пользователя:"
        )

        await callback.message.edit_text(
            text, reply_markup=paginator.get_keyboard(), parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Error showing users list: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки списка", show_alert=True)


# ==================== ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ ====================


@admin_router.callback_query(F.data.startswith("user_profile_"))
async def show_user_profile(callback: CallbackQuery):
    """Показать профиль пользователя"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    user_id = int(callback.data.split("_")[-1])

    try:
        async with get_db() as db:
            # Получаем информацию о пользователе
            async with db.execute(
                "SELECT user_id, username, first_name, join_date, has_payment_attempt FROM users WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                user = await cursor.fetchone()

            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                return

            username = user[1] or ""
            first_name = user[2] or ""
            join_date = user[3]
            has_payment = user[4]

            # Проверка подписки
            sub = await get_subscription(user_id)

            # Количество отмен подписок
            async with db.execute(
                "SELECT COUNT(*) FROM cancellations WHERE user_id = ?", (user_id,)
            ) as cursor:
                cancellations_count = (await cursor.fetchone())[0]

            profile_text = _build_profile_text(
                user_id=user_id,
                first_name=first_name,
                username=username,
                join_date=join_date,
                has_payment=has_payment,
                cancellations_count=cancellations_count,
                sub=sub,
            )

            await callback.message.edit_text(
                profile_text,
                reply_markup=user_profile_keyboard(user_id),
                parse_mode="HTML",
            )
            await callback.answer()

    except Exception as e:
        logger.error(f"Error showing user profile: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки профиля", show_alert=True)


@admin_router.callback_query(F.data.startswith("sub_info_"))
async def show_subscription_details(callback: CallbackQuery):
    """Детальная информация о подписке"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    user_id = int(callback.data.split("_")[-1])

    try:
        sub = await get_subscription(user_id)

        if not sub:
            await callback.answer("❌ У пользователя нет подписки", show_alert=True)
            return

        details = (
            f"💎 <b>ДЕТАЛИ ПОДПИСКИ</b>\n\n"
            f"👤 User ID: <code>{user_id}</code>\n\n"
            f"📊 <b>Статус:</b> {escape(str(sub['status']))}\n"
            f"💳 <b>Провайдер:</b> {escape(str(sub['payment_provider']))}\n"
            f"🔗 <b>Invite Link:</b> {escape(str(sub.get('invite_link', 'Нет')))}\n"
            f"📅 <b>Истекает:</b> {sub['expires_at'].strftime('%d.%m.%Y %H:%M')}\n"
            f"🆔 <b>Payment Sub ID:</b> {escape(str(sub.get('stripe_subscription_id', 'N/A')))}\n"
            f"👤 <b>Customer ID:</b> {escape(str(sub.get('stripe_customer_id', 'N/A')))}"
        )

        await callback.message.edit_text(
            details, reply_markup=user_profile_keyboard(user_id), parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Error showing subscription details: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@admin_router.callback_query(F.data.startswith("message_user_"))
async def message_user_prompt(callback: CallbackQuery, state: FSMContext):
    """Написать пользователю"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    user_id = int(callback.data.split("_")[-1])

    await callback.message.edit_text(
        f"💬 <b>ОТПРАВКА СООБЩЕНИЯ</b>\n\n"
        f"Получатель: User ID <code>{user_id}</code>\n\n"
        f"Отправьте текст сообщения:",
        reply_markup=user_profile_keyboard(user_id),
        parse_mode="HTML",
    )
    await state.update_data(message_target_user=user_id)
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.answer()


# ==================== СТАТИСТИКА ====================


@admin_router.callback_query(F.data == "admin_stats")
async def show_detailed_stats(callback: CallbackQuery):
    """Детальная статистика"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    try:
        async with get_db() as db:
            # Общие данные
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                total_users = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE status = 'active' AND expires_at > ?",
                (datetime.now().isoformat(),),
            ) as cursor:
                active_subs = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE status = 'cancelled'"
            ) as cursor:
                cancelled_subs = (await cursor.fetchone())[0]

            # Статистика по дням
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE DATE(join_date) = DATE('now')"
            ) as cursor:
                today_users = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE DATE(created_at) = DATE('now')"
            ) as cursor:
                today_subs = (await cursor.fetchone())[0]

            # Доход
            from config import SUBSCRIPTION_PRICE

            revenue = active_subs * SUBSCRIPTION_PRICE

            stats_text = (
                f"📊 <b>ДЕТАЛЬНАЯ СТАТИСТИКА</b>\n\n"
                f"👥 <b>Пользователи:</b>\n"
                f"├ Всего: {total_users}\n"
                f"└ Новых сегодня: {today_users}\n\n"
                f"💎 <b>Подписки:</b>\n"
                f"├ Активных: {active_subs}\n"
                f"├ Отмененных: {cancelled_subs}\n"
                f"└ Оформлено сегодня: {today_subs}\n\n"
                f"💰 <b>Приблизительный доход:</b>\n"
                f"└ ${revenue:.2f} (активные подписки)\n\n"
                f"📅 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )

            await callback.message.edit_text(
                stats_text, reply_markup=back_to_admin_keyboard(), parse_mode="HTML"
            )
            await callback.answer()

    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        await callback.answer("❌ Ошибка получения статистики", show_alert=True)


# ==================== РАССЫЛКА ====================


@admin_router.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    """Начать рассылку"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    await callback.message.edit_text(
        "📢 <b>МАССОВАЯ РАССЫЛКА</b>\n\n"
        "Отправьте текст сообщения для рассылки всем пользователям.\n\n"
        "⚠️ Поддерживается HTML-форматирование.",
        reply_markup=back_to_admin_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_broadcast)
async def confirm_broadcast(message: Message, state: FSMContext, bot: Bot):
    """Подтверждение рассылки"""
    data = await state.get_data()
    target_user = data.get("message_target_user")

    # Если это отправка конкретному пользователю
    if target_user:
        try:
            await bot.send_message(target_user, message.text)
            await message.answer(
                f"✅ Сообщение отправлено пользователю {target_user}",
                reply_markup=back_to_admin_keyboard(),
            )
            logger.info(f"Admin {message.from_user.id} sent message to {target_user}")
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            await message.answer(
                "❌ Не удалось отправить сообщение",
                reply_markup=back_to_admin_keyboard(),
            )
        await state.clear()
        return

    # Массовая рассылка
    await state.update_data(broadcast_text=message.text)

    users = await get_all_users()
    await message.answer(
        f"📢 <b>ПОДТВЕРЖДЕНИЕ РАССЫЛКИ</b>\n\n"
        f"Получателей: {len(users)}\n\n"
        f"<b>Текст сообщения:</b>\n{escape(message.text)}\n\n"
        f"Отправить?",
        reply_markup=confirm_broadcast_keyboard(),
        parse_mode="HTML",
    )


@admin_router.callback_query(F.data == "broadcast_confirm")
async def execute_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Выполнить рассылку"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    data = await state.get_data()
    broadcast_text = data.get("broadcast_text")

    if not broadcast_text:
        await callback.answer("❌ Текст не найден", show_alert=True)
        return

    users = await get_all_users()
    success = 0
    failed = 0

    await callback.message.edit_text(
        f"📤 Отправка сообщения {len(users)} пользователям...\n\nПожалуйста, подождите."
    )

    for user in users:
        try:
            await bot.send_message(user["user_id"], broadcast_text)
            success += 1
            import asyncio

            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.warning(f"Failed to send to {user['user_id']}: {e}")

    await callback.message.edit_text(
        f"✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b>\n\n"
        f"✅ Отправлено: {success}\n"
        f"❌ Ошибок: {failed}\n"
        f"📊 Всего: {len(users)}",
        reply_markup=back_to_admin_keyboard(),
        parse_mode="HTML",
    )

    await state.clear()
    await callback.answer("✅ Готово!")
    logger.info(f"Broadcast completed: {success} sent, {failed} failed")


# ==================== LEGACY-УВЕДОМЛЕНИЯ ====================


@admin_router.callback_query(F.data == "admin_legacy_notify")
async def start_legacy_notify(callback: CallbackQuery, state: FSMContext):
    """Запуск уведомления клиентов из старой базы по username."""
    if callback.from_user.id not in ADMIN_IDS:
        return

    await callback.message.edit_text(
        "🔔 <b>УВЕДОМЛЕНИЕ СТАРОЙ БАЗЫ</b>\n\n"
        "Отправьте список username (через пробел, запятую или с новой строки).\n"
        "Пример: <code>@alice @bob charlie</code>",
        reply_markup=back_to_admin_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.waiting_for_legacy_usernames)
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_legacy_usernames)
async def process_legacy_notify(message: Message, state: FSMContext, bot: Bot):
    """Отправка уведомлений о продлении подписки пользователям по username."""
    if message.from_user.id not in ADMIN_IDS:
        return

    usernames = _parse_usernames(message.text or "")
    if not usernames:
        await message.answer(
            "❌ Не нашел ни одного валидного username. Попробуйте снова."
        )
        return

    placeholders = ",".join(["?"] * len(usernames))

    async with get_db() as db:
        async with db.execute(
            f"SELECT user_id, username FROM users WHERE lower(username) IN ({placeholders})",
            usernames,
        ) as cursor:
            rows = await cursor.fetchall()

    found = {str(row[1]).lower(): row[0] for row in rows if row[1]}
    missed = [u for u in usernames if u not in found]

    payment_url = await PaymentFactory.create_payment(message.from_user.id)
    if not payment_url:
        await message.answer(
            "❌ Не удалось получить ссылку оплаты. Проверьте платежный провайдер.",
            reply_markup=back_to_admin_keyboard(),
        )
        await state.clear()
        return

    sent = 0
    failed = 0

    for username in usernames:
        user_id = found.get(username)
        if not user_id:
            continue
        try:
            await bot.send_message(
                user_id,
                format_message("renewal_offer_expired", payment_url=payment_url),
                reply_markup=renewal_offer_keyboard(),
                parse_mode="HTML",
            )
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning("Failed to notify user %s (@%s): %s", user_id, username, e)

    missed_text = ", ".join(f"@{u}" for u in missed[:30]) if missed else "нет"
    await message.answer(
        "✅ <b>Рассылка старой базе завершена</b>\n\n"
        f"Введено username: {len(usernames)}\n"
        f"Найдено в БД: {len(found)}\n"
        f"Отправлено: {sent}\n"
        f"Ошибок отправки: {failed}\n"
        f"Не найдены: {len(missed)}\n"
        f"Список (первые 30): {missed_text}",
        reply_markup=back_to_admin_keyboard(),
        parse_mode="HTML",
    )
    await state.clear()


# ==================== ПОИСК ПОЛЬЗОВАТЕЛЯ ====================


@admin_router.callback_query(F.data == "admin_search")
async def start_user_search(callback: CallbackQuery, state: FSMContext):
    """Поиск пользователя"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    await callback.message.edit_text(
        "🔍 <b>ПОИСК ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Отправьте:\n"
        "• User ID (например: 123456789)\n"
        "• Username (например: @username)",
        reply_markup=back_to_admin_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.waiting_for_user_search)
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_user_search)
async def process_user_search(message: Message, state: FSMContext):
    """Обработка поиска"""
    query = message.text.strip().lstrip("@")

    try:
        async with get_db() as db:
            if query.isdigit():
                async with db.execute(
                    "SELECT user_id FROM users WHERE user_id = ?", (int(query),)
                ) as cursor:
                    user = await cursor.fetchone()
            else:
                async with db.execute(
                    "SELECT user_id FROM users WHERE username = ?", (query,)
                ) as cursor:
                    user = await cursor.fetchone()

            if not user:
                await message.answer(
                    "❌ Пользователь не найден", reply_markup=back_to_admin_keyboard()
                )
                await state.clear()
                return

            user_id = user[0]

            # Показываем профиль найденного пользователя
            await state.clear()

            # Создаем фейковый callback для переиспользования функции
            from aiogram.types import CallbackQuery as CQ

            fake_callback = type(
                "obj",
                (object,),
                {
                    "message": message,
                    "from_user": message.from_user,
                    "data": f"user_profile_{user_id}",
                    "answer": lambda text="", show_alert=False: None,
                },
            )()

            # Используем существующую функцию показа профиля
            await show_user_profile_from_search(message, user_id)

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        await message.answer("❌ Ошибка поиска", reply_markup=back_to_admin_keyboard())
        await state.clear()


async def show_user_profile_from_search(message: Message, user_id: int):
    """Показать профиль после поиска"""
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT user_id, username, first_name, join_date, has_payment_attempt FROM users WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                user = await cursor.fetchone()

            if not user:
                await message.answer("❌ Пользователь не найден")
                return

            username = user[1] or ""
            first_name = user[2] or ""
            join_date = user[3]
            has_payment = user[4]

            sub = await get_subscription(user_id)

            async with db.execute(
                "SELECT COUNT(*) FROM cancellations WHERE user_id = ?", (user_id,)
            ) as cursor:
                cancellations_count = (await cursor.fetchone())[0]

            profile_text = _build_profile_text(
                user_id=user_id,
                first_name=first_name,
                username=username,
                join_date=join_date,
                has_payment=has_payment,
                cancellations_count=cancellations_count,
                sub=sub,
            )

            await message.answer(
                profile_text,
                reply_markup=user_profile_keyboard(user_id),
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки профиля")


# ==================== УПРАВЛЕНИЕ ПОДПИСКАМИ ====================


@admin_router.callback_query(F.data == "admin_give_sub")
async def start_manual_subscription(callback: CallbackQuery, state: FSMContext):
    """Выдать подписку вручную"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    await callback.message.edit_text(
        "💎 <b>ВЫДАЧА ПОДПИСКИ</b>\n\nОтправьте User ID пользователя:",
        reply_markup=back_to_admin_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.waiting_for_manual_sub_user)
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_manual_sub_user)
async def ask_subscription_days(message: Message, state: FSMContext):
    """Спросить количество дней"""
    if not message.text.isdigit():
        await message.answer("❌ Отправьте корректный User ID (число)")
        return

    user_id = int(message.text)
    await state.update_data(target_user_id=user_id)

    await message.answer(
        f"💎 Выдача подписки для User ID: <code>{user_id}</code>\n\n"
        f"Отправьте количество дней (по умолчанию: {SUBSCRIPTION_DAYS}):",
        reply_markup=back_to_admin_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.waiting_for_manual_sub_days)


@admin_router.message(AdminStates.waiting_for_manual_sub_days)
async def give_manual_subscription(message: Message, state: FSMContext, bot: Bot):
    """Выдать подписку"""
    from datetime import timedelta

    data = await state.get_data()
    target_user_id = data.get("target_user_id")

    days = SUBSCRIPTION_DAYS
    if message.text.isdigit():
        days = int(message.text)

    try:
        invite_link = await _create_invite_link(bot, f"Admin_{target_user_id}")

        await create_subscription(
            user_id=target_user_id,
            payment_provider="admin_manual",
            invite_link=invite_link,
            days=days,
        )

        try:
            await bot.send_message(
                target_user_id,
                f"🎁 <b>Вам выдана подписка!</b>\n\n"
                f"⏰ Срок: {days} дней\n"
                f"🔗 Ссылка на канал:\n{invite_link}\n\n"
                f"⚠️ Ссылка действительна 24 часа",
                parse_mode="HTML",
            )
        except Exception:
            pass

        await message.answer(
            f"✅ Подписка выдана!\n\n"
            f"👤 User ID: {target_user_id}\n"
            f"⏰ Дней: {days}\n"
            f"🔗 Ссылка: {invite_link}",
            reply_markup=back_to_admin_keyboard(),
        )

        logger.info(
            f"Admin {message.from_user.id} gave subscription to {target_user_id} for {days} days"
        )

    except RuntimeError as e:
        logger.error(f"Failed to give subscription: {e}")
        await message.answer(str(e), reply_markup=back_to_admin_keyboard(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to give subscription: {e}", exc_info=True)
        await message.answer(
            f"❌ Ошибка выдачи подписки: {e}", reply_markup=back_to_admin_keyboard()
        )

    await state.clear()


@admin_router.callback_query(F.data.startswith("give_sub_"))
async def give_subscription_from_profile(callback: CallbackQuery, bot: Bot):
    """Выдать подписку из профиля"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    user_id = int(callback.data.split("_")[-1])

    try:
        invite_link = await _create_invite_link(bot, f"Admin_{user_id}")

        await create_subscription(
            user_id=user_id,
            payment_provider="admin_manual",
            invite_link=invite_link,
            days=SUBSCRIPTION_DAYS,
        )

        try:
            await bot.send_message(
                user_id,
                f"🎁 <b>Вам выдана подписка!</b>\n\n"
                f"⏰ Срок: {SUBSCRIPTION_DAYS} дней\n"
                f"🔗 Ссылка на канал:\n{invite_link}\n\n"
                f"⚠️ Ссылка действительна 24 часа",
                parse_mode="HTML",
            )
        except Exception:
            pass

        await callback.answer(
            f"✅ Подписка выдана на {SUBSCRIPTION_DAYS} дней", show_alert=True
        )

        # Обновляем профиль
        await show_user_profile(callback)

        logger.info(f"Admin {callback.from_user.id} gave subscription to {user_id}")

    except RuntimeError as e:
        logger.error(f"Failed to give subscription: {e}")
        await callback.message.answer(str(e), parse_mode="HTML", reply_markup=back_to_admin_keyboard())
        await callback.answer("❌ Ошибка", show_alert=False)
    except Exception as e:
        logger.error(f"Failed to give subscription: {e}", exc_info=True)
        await callback.answer(f"❌ Ошибка: {e}"[:200], show_alert=True)


@admin_router.callback_query(F.data.startswith("revoke_sub_"))
async def revoke_subscription(callback: CallbackQuery):
    """Отозвать подписку"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    user_id = int(callback.data.split("_")[-1])

    try:
        await cancel_subscription(user_id)
        await callback.answer("✅ Подписка отозвана", show_alert=True)

        # Обновляем профиль
        await show_user_profile(callback)

        logger.info(f"Admin {callback.from_user.id} revoked subscription for {user_id}")

    except Exception as e:
        logger.error(f"Failed to revoke: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


# ==================== ПРИЧИНЫ ОТМЕН ====================


@admin_router.callback_query(F.data == "admin_cancellations")
async def show_cancellations(callback: CallbackQuery):
    """Показать причины отмен"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT username, reason, cancelled_at FROM cancellations ORDER BY cancelled_at DESC LIMIT 20"
            ) as cursor:
                cancellations = await cursor.fetchall()

        if not cancellations:
            await callback.message.edit_text(
                "📋 Причин отмен пока нет", reply_markup=back_to_admin_keyboard()
            )
            await callback.answer()
            return

        text = "📋 <b>ПОСЛЕДНИЕ ОТМЕНЫ ПОДПИСОК</b>\n\n"
        for i, row in enumerate(cancellations, 1):
            username = escape(row[0] or "Неизвестно")
            reason = row[1][:50] + "..." if len(row[1]) > 50 else row[1]
            reason = escape(reason)
            date = row[2]
            text += f"{i}. @{username}\n💬 {reason}\n📅 {date}\n\n"

        await callback.message.edit_text(
            text, reply_markup=back_to_admin_keyboard(), parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Error getting cancellations: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


# ==================== ЭКСПОРТ ====================


@admin_router.callback_query(F.data == "admin_export")
async def export_data(callback: CallbackQuery):
    """Экспорт всех пользователей с данными подписок в CSV"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    try:
        from aiogram.types import BufferedInputFile

        async with get_db() as db:
            async with db.execute("""
                SELECT
                    u.user_id,
                    u.username,
                    u.first_name,
                    u.join_date,
                    u.has_payment_attempt,
                    COALESCE(s.status, 'none') AS sub_status,
                    s.expires_at,
                    s.payment_provider
                FROM users u
                LEFT JOIN subscriptions s ON u.user_id = s.user_id
                ORDER BY u.join_date DESC
            """) as cursor:
                rows = await cursor.fetchall()

        lines = ["user_id,username,first_name,join_date,has_payment_attempt,subscription_status,expires_at,payment_provider"]
        for row in rows:
            user_id, username, first_name, join_date, has_attempt, sub_status, expires_at, provider = row
            lines.append(
                f"{user_id},"
                f"{_csv_escape(username)},"
                f"{_csv_escape(first_name)},"
                f"{join_date or ''},"
                f"{'yes' if has_attempt else 'no'},"
                f"{sub_status},"
                f"{expires_at or ''},"
                f"{provider or ''}"
            )

        csv_bytes = "\n".join(lines).encode("utf-8-sig")  # utf-8-sig для корректного открытия в Excel
        filename = f"users_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

        file = BufferedInputFile(csv_bytes, filename=filename)
        await callback.message.answer_document(
            document=file,
            caption=(
                f"📥 <b>Экспорт пользователей</b>\n\n"
                f"👥 Всего записей: {len(rows)}\n"
                f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            ),
            parse_mode="HTML",
        )
        await callback.answer("✅ Файл отправлен")

    except Exception as e:
        logger.error(f"Export error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка экспорта", show_alert=True)


def _csv_escape(value: str) -> str:
    """Экранирует значение для CSV (оборачивает в кавычки если нужно)."""
    if not value:
        return ""
    value = str(value)
    if "," in value or '"' in value or "\n" in value:
        return '"' + value.replace('"', '""') + '"'
    return value


# ==================== БЕКАП ====================


@admin_router.callback_query(F.data == "admin_backup")
async def trigger_backup(callback: CallbackQuery):
    """Создать бекап базы данных и отправить файл администратору"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    await callback.answer("⏳ Создаю бекап...")

    try:
        from aiogram.types import FSInputFile

        backup_path = await backup_database()

        if not backup_path:
            await callback.message.answer(
                "❌ Не удалось создать бекап. Проверьте логи.",
                reply_markup=back_to_admin_keyboard(),
            )
            return

        file = FSInputFile(str(backup_path), filename=backup_path.name)
        await callback.message.answer_document(
            document=file,
            caption=(
                f"💾 <b>Бекап базы данных</b>\n\n"
                f"📁 Файл: <code>{backup_path.name}</code>\n"
                f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            ),
            parse_mode="HTML",
        )
        logger.info(f"Admin {callback.from_user.id} requested manual backup: {backup_path}")

    except Exception as e:
        logger.error(f"Backup error: {e}", exc_info=True)
        await callback.message.answer(
            "❌ Ошибка при создании бекапа",
            reply_markup=back_to_admin_keyboard(),
        )


# ==================== ДИАГНОСТИКА И ТЕСТ ОПЛАТЫ ====================


def _diagnostics_keyboard(channel_ok: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_diagnostics")],
        [InlineKeyboardButton(text="💳 Создать тестовую ссылку Stripe", callback_data="admin_test_stripe_link")],
    ]
    if channel_ok:
        buttons.append(
            [InlineKeyboardButton(text="🎁 Симулировать выдачу подписки себе", callback_data="admin_test_give_sub")]
        )
    buttons.append(
        [InlineKeyboardButton(text="🔙 Назад в админку", callback_data="admin_panel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@admin_router.callback_query(F.data == "admin_diagnostics")
async def show_diagnostics(callback: CallbackQuery, bot: Bot):
    """Диагностика: Stripe, канал, webhook"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    await callback.answer("⏳ Проверяю...")

    import stripe as stripe_lib
    from config import STRIPE_PRICE_ID, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, WEBHOOK_PATH

    lines = ["🔍 <b>ДИАГНОСТИКА СИСТЕМЫ</b>\n"]

    # ── Stripe API key ──────────────────────────────────────
    if not STRIPE_SECRET_KEY:
        lines.append("❌ <b>Stripe API ключ:</b> не задан")
    elif STRIPE_SECRET_KEY.startswith("sk_test_"):
        lines.append("⚠️ <b>Stripe API ключ:</b> тестовый режим <code>sk_test_…</code>")
    elif STRIPE_SECRET_KEY.startswith("sk_live_"):
        lines.append("✅ <b>Stripe API ключ:</b> боевой режим <code>sk_live_…</code>")
    else:
        lines.append("⚠️ <b>Stripe API ключ:</b> задан, формат нестандартный")

    # ── Price ID ─────────────────────────────────────────────
    if not STRIPE_PRICE_ID:
        lines.append("❌ <b>Price ID:</b> не задан (STRIPE_PRICE_ID)")
    elif STRIPE_SECRET_KEY:
        try:
            price = stripe_lib.Price.retrieve(STRIPE_PRICE_ID)
            amount = f"{price.unit_amount / 100:.2f}" if price.unit_amount else "?"
            currency = (price.currency or "").upper()
            lines.append(f"✅ <b>Price ID:</b> {amount} {currency} — найден в Stripe")
        except stripe_lib.StripeError as e:
            lines.append(f"❌ <b>Price ID:</b> ошибка Stripe — {getattr(e, 'user_message', None) or e}")
        except Exception as e:
            lines.append(f"❌ <b>Price ID:</b> {e}")
    else:
        lines.append(f"⚠️ <b>Price ID:</b> задан, но ключ API не проверен")

    # ── Webhook Secret ────────────────────────────────────────
    if not STRIPE_WEBHOOK_SECRET:
        lines.append("⚠️ <b>Webhook Secret:</b> не задан — подпись не верифицируется!")
    else:
        lines.append("✅ <b>Webhook Secret:</b> задан")

    # ── Webhook path ──────────────────────────────────────────
    lines.append(f"🌐 <b>Webhook path:</b> <code>{WEBHOOK_PATH}</code>")
    lines.append("   ↳ Настройте этот путь в Stripe Dashboard → Webhooks")
    lines.append("   ↳ Событие: <code>checkout.session.completed</code>\n")

    # ── Канал ─────────────────────────────────────────────────
    channel_ok = False
    invite_ok = False

    try:
        chat = await bot.get_chat(int(CHANNEL_ID))
        lines.append(f"✅ <b>Канал:</b> {escape(chat.title or str(chat.id))}")
        channel_ok = True
    except Exception as e:
        lines.append(f"❌ <b>Канал не найден:</b> {escape(str(e))}")
        lines.append("   ↳ Проверьте CHANNEL_ID в .env (формат: <code>-100XXXXXXXXXX</code>)")

    # ── Права на invite-ссылки ────────────────────────────────
    if channel_ok:
        try:
            from datetime import timedelta
            test_invite = await bot.create_chat_invite_link(
                chat_id=int(CHANNEL_ID),
                member_limit=1,
                expire_date=timedelta(hours=1),
                name="DiagCheck",
            )
            await bot.revoke_chat_invite_link(int(CHANNEL_ID), test_invite.invite_link)
            lines.append("✅ <b>Invite-ссылки:</b> бот может создавать (права администратора OK)")
            invite_ok = True
        except Exception as e:
            lines.append(f"❌ <b>Invite-ссылки:</b> {escape(str(e))}")
            lines.append("   ↳ Дайте боту права администратора с разрешением «Приглашать участников»")

    channel_ok = channel_ok and invite_ok

    text = "\n".join(lines)
    await callback.message.edit_text(
        text,
        reply_markup=_diagnostics_keyboard(channel_ok),
        parse_mode="HTML",
    )


@admin_router.callback_query(F.data == "admin_test_stripe_link")
async def test_stripe_link(callback: CallbackQuery):
    """Создать реальную Stripe Checkout Session и отправить ссылку себе"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    await callback.answer("⏳ Создаю ссылку...")

    user_id = callback.from_user.id
    try:
        payment_url = await PaymentFactory.create_payment(user_id)
    except Exception as e:
        await callback.message.answer(
            f"❌ Ошибка при создании Stripe сессии:\n<code>{escape(str(e))}</code>\n\n"
            "Проверьте <b>STRIPE_SECRET_KEY</b> и <b>STRIPE_PRICE_ID</b> в .env",
            reply_markup=back_to_admin_keyboard(),
            parse_mode="HTML",
        )
        return

    if not payment_url:
        await callback.message.answer(
            "❌ Stripe вернул пустой URL.\n"
            "Проверьте <b>STRIPE_SECRET_KEY</b> и <b>STRIPE_PRICE_ID</b> в .env",
            reply_markup=back_to_admin_keyboard(),
            parse_mode="HTML",
        )
        return

    mode_hint = ""
    from config import STRIPE_SECRET_KEY
    if STRIPE_SECRET_KEY.startswith("sk_test_"):
        mode_hint = "\n\n🃏 <b>Тестовая карта:</b> <code>4242 4242 4242 4242</code>, любые дата/CVV"

    await callback.message.answer(
        f"💳 <b>Тестовая Stripe-ссылка создана</b>\n\n"
        f"User ID в metadata: <code>{user_id}</code>\n"
        f"После оплаты webhook должен выдать вам подписку.{mode_hint}\n\n"
        f'💳 <a href="{payment_url}">Перейти к оплате</a>',
        reply_markup=back_to_admin_keyboard(),
        parse_mode="HTML",
    )
    logger.info(f"Admin {user_id} created test Stripe link: {payment_url}")


@admin_router.callback_query(F.data == "admin_test_give_sub")
async def test_give_subscription(callback: CallbackQuery, bot: Bot):
    """Симулировать выдачу подписки администратору (без оплаты)"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    user_id = callback.from_user.id
    await callback.answer("⏳ Симулирую выдачу...")

    try:
        invite_link = await _create_invite_link(bot, f"Test_{user_id}")

        session_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        await create_subscription(
            user_id=user_id,
            payment_provider="test_simulation",
            invite_link=invite_link,
            days=1,
            stripe_subscription_id=session_id,
        )

        await callback.message.answer(
            f"✅ <b>Симуляция успешна!</b>\n\n"
            f"Ссылка на канал:\n{invite_link}\n\n"
            f"⚠️ Тестовая подписка на <b>1 день</b>\n"
            f"ID: <code>{session_id}</code>",
            reply_markup=back_to_admin_keyboard(),
            parse_mode="HTML",
        )
        logger.info(f"Admin {user_id} simulated subscription delivery")

    except RuntimeError as e:
        await callback.message.answer(str(e), reply_markup=back_to_admin_keyboard(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Simulation error: {e}", exc_info=True)
        await callback.message.answer(
            f"❌ Ошибка симуляции:\n<code>{escape(str(e))}</code>",
            reply_markup=back_to_admin_keyboard(),
            parse_mode="HTML",
        )
