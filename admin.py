"""
Админ-панель для управления ботом
"""

import logging
from html import escape
from datetime import datetime
from typing import Dict, List

from aiogram import F, Router
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

logger = logging.getLogger(__name__)
admin_router = Router()

# ==================== STATES ====================


class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_user_search = State()
    waiting_for_manual_sub_user = State()
    waiting_for_manual_sub_days = State()


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
            [
                InlineKeyboardButton(
                    text="👥 Список пользователей", callback_data="admin_users_list"
                )
            ],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
            [
                InlineKeyboardButton(
                    text="🔍 Найти пользователя", callback_data="admin_search"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 Выдать подписку", callback_data="admin_give_sub"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Причины отмен", callback_data="admin_cancellations"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📥 Экспорт данных", callback_data="admin_export"
                )
            ],
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


# ==================== HANDLERS ====================


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Открыть админ-панель"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к админ-панели")
        return

    await message.answer(
        "🔧 **АДМИН-ПАНЕЛЬ**\n\nВыберите действие:", reply_markup=admin_main_keyboard()
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
        "🔧 **АДМИН-ПАНЕЛЬ**\n\nВыберите действие:", reply_markup=admin_main_keyboard()
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
            f"👥 **СПИСОК ПОЛЬЗОВАТЕЛЕЙ**\n\n"
            f"📊 Всего: {len(users)}\n"
            f"📄 Страница {page + 1} из {paginator.total_pages}\n\n"
            f"Выберите пользователя:"
        )

        await callback.message.edit_text(text, reply_markup=paginator.get_keyboard())
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
            f"💎 **ДЕТАЛИ ПОДПИСКИ**\n\n"
            f"👤 User ID: `{user_id}`\n\n"
            f"📊 **Статус:** {sub['status']}\n"
            f"💳 **Провайдер:** {sub['payment_provider']}\n"
            f"🔗 **Invite Link:** {sub.get('invite_link', 'Нет')}\n"
            f"📅 **Истекает:** {sub['expires_at'].strftime('%d.%m.%Y %H:%M')}\n"
            f"🆔 **Payment Sub ID:** {sub.get('stripe_subscription_id', 'N/A')}\n"
            f"👤 **Customer ID:** {sub.get('stripe_customer_id', 'N/A')}"
        )

        await callback.message.edit_text(
            details, reply_markup=user_profile_keyboard(user_id)
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
        f"💬 **ОТПРАВКА СООБЩЕНИЯ**\n\n"
        f"Получатель: User ID `{user_id}`\n\n"
        f"Отправьте текст сообщения:",
        reply_markup=user_profile_keyboard(user_id),
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
                f"📊 **ДЕТАЛЬНАЯ СТАТИСТИКА**\n\n"
                f"👥 **Пользователи:**\n"
                f"├ Всего: {total_users}\n"
                f"└ Новых сегодня: {today_users}\n\n"
                f"💎 **Подписки:**\n"
                f"├ Активных: {active_subs}\n"
                f"├ Отмененных: {cancelled_subs}\n"
                f"└ Оформлено сегодня: {today_subs}\n\n"
                f"💰 **Приблизительный доход:**\n"
                f"└ ${revenue:.2f} (активные подписки)\n\n"
                f"📅 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )

            await callback.message.edit_text(
                stats_text, reply_markup=back_to_admin_keyboard()
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
        "📢 **МАССОВАЯ РАССЫЛКА**\n\n"
        "Отправьте текст сообщения для рассылки всем пользователям.\n\n"
        "⚠️ Поддерживается форматирование Markdown.",
        reply_markup=back_to_admin_keyboard(),
    )
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_broadcast)
async def confirm_broadcast(message: Message, state: FSMContext):
    """Подтверждение рассылки"""
    data = await state.get_data()
    target_user = data.get("message_target_user")

    # Если это отправка конкретному пользователю
    if target_user:
        from bot import bot

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
        f"📢 **ПОДТВЕРЖДЕНИЕ РАССЫЛКИ**\n\n"
        f"Получателей: {len(users)}\n\n"
        f"**Текст сообщения:**\n{message.text}\n\n"
        f"Отправить?",
        reply_markup=confirm_broadcast_keyboard(),
    )


@admin_router.callback_query(F.data == "broadcast_confirm")
async def execute_broadcast(callback: CallbackQuery, state: FSMContext):
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

    from bot import bot

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
        f"✅ **РАССЫЛКА ЗАВЕРШЕНА**\n\n"
        f"✅ Отправлено: {success}\n"
        f"❌ Ошибок: {failed}\n"
        f"📊 Всего: {len(users)}",
        reply_markup=back_to_admin_keyboard(),
    )

    await state.clear()
    await callback.answer("✅ Готово!")
    logger.info(f"Broadcast completed: {success} sent, {failed} failed")


# ==================== ПОИСК ПОЛЬЗОВАТЕЛЯ ====================


@admin_router.callback_query(F.data == "admin_search")
async def start_user_search(callback: CallbackQuery, state: FSMContext):
    """Поиск пользователя"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    await callback.message.edit_text(
        "🔍 **ПОИСК ПОЛЬЗОВАТЕЛЯ**\n\n"
        "Отправьте:\n"
        "• User ID (например: 123456789)\n"
        "• Username (например: @username)",
        reply_markup=back_to_admin_keyboard(),
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
        "💎 **ВЫДАЧА ПОДПИСКИ**\n\nОтправьте User ID пользователя:",
        reply_markup=back_to_admin_keyboard(),
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
        f"💎 Выдача подписки для User ID: `{user_id}`\n\n"
        f"Отправьте количество дней (по умолчанию: {SUBSCRIPTION_DAYS}):",
        reply_markup=back_to_admin_keyboard(),
    )
    await state.set_state(AdminStates.waiting_for_manual_sub_days)


@admin_router.message(AdminStates.waiting_for_manual_sub_days)
async def give_manual_subscription(message: Message, state: FSMContext):
    """Выдать подписку"""
    from datetime import timedelta

    from bot import bot

    data = await state.get_data()
    target_user_id = data.get("target_user_id")

    days = SUBSCRIPTION_DAYS
    if message.text.isdigit():
        days = int(message.text)

    try:
        invite = await bot.create_chat_invite_link(
            chat_id=int(CHANNEL_ID),
            member_limit=1,
            expire_date=timedelta(days=1),
            name=f"Admin_{target_user_id}",
        )

        await create_subscription(
            user_id=target_user_id,
            payment_provider="admin_manual",
            invite_link=invite.invite_link,
            days=days,
        )

        try:
            await bot.send_message(
                target_user_id,
                f"🎁 **Вам выдана подписка!**\n\n"
                f"⏰ Срок: {days} дней\n"
                f"🔗 Ссылка на канал:\n{invite.invite_link}\n\n"
                f"⚠️ Ссылка действительна 24 часа",
            )
        except:
            pass

        await message.answer(
            f"✅ Подписка выдана!\n\n"
            f"👤 User ID: {target_user_id}\n"
            f"⏰ Дней: {days}\n"
            f"🔗 Ссылка: {invite.invite_link}",
            reply_markup=back_to_admin_keyboard(),
        )

        logger.info(
            f"Admin {message.from_user.id} gave subscription to {target_user_id} for {days} days"
        )

    except Exception as e:
        logger.error(f"Failed to give subscription: {e}", exc_info=True)
        await message.answer(
            "❌ Ошибка выдачи подписки", reply_markup=back_to_admin_keyboard()
        )

    await state.clear()


@admin_router.callback_query(F.data.startswith("give_sub_"))
async def give_subscription_from_profile(callback: CallbackQuery):
    """Выдать подписку из профиля"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    from datetime import timedelta

    from bot import bot

    user_id = int(callback.data.split("_")[-1])

    try:
        invite = await bot.create_chat_invite_link(
            chat_id=int(CHANNEL_ID),
            member_limit=1,
            expire_date=timedelta(days=1),
            name=f"Admin_{user_id}",
        )

        await create_subscription(
            user_id=user_id,
            payment_provider="admin_manual",
            invite_link=invite.invite_link,
            days=SUBSCRIPTION_DAYS,
        )

        try:
            await bot.send_message(
                user_id,
                f"🎁 **Вам выдана подписка!**\n\n"
                f"⏰ Срок: {SUBSCRIPTION_DAYS} дней\n"
                f"🔗 Ссылка на канал:\n{invite.invite_link}\n\n"
                f"⚠️ Ссылка действительна 24 часа",
            )
        except:
            pass

        await callback.answer(
            f"✅ Подписка выдана на {SUBSCRIPTION_DAYS} дней", show_alert=True
        )

        # Обновляем профиль
        await show_user_profile(callback)

        logger.info(f"Admin {callback.from_user.id} gave subscription to {user_id}")

    except Exception as e:
        logger.error(f"Failed to give subscription: {e}", exc_info=True)
        await callback.answer("❌ Ошибка выдачи подписки", show_alert=True)


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

        text = "📋 **ПОСЛЕДНИЕ ОТМЕНЫ ПОДПИСОК**\n\n"
        for i, row in enumerate(cancellations, 1):
            username = row[0] or "Неизвестно"
            reason = row[1][:50] + "..." if len(row[1]) > 50 else row[1]
            date = row[2]
            text += f"{i}. @{username}\n💬 {reason}\n📅 {date}\n\n"

        await callback.message.edit_text(text, reply_markup=back_to_admin_keyboard())
        await callback.answer()

    except Exception as e:
        logger.error(f"Error getting cancellations: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


# ==================== ЭКСПОРТ ====================


@admin_router.callback_query(F.data == "admin_export")
async def export_data(callback: CallbackQuery):
    """Экспорт данных"""
    if callback.from_user.id not in ADMIN_IDS:
        return

    try:
        users = await get_all_users()

        csv_data = "user_id,username\n"
        for user in users:
            csv_data += f"{user['user_id']},{user['username']}\n"

        from aiogram.types import BufferedInputFile

        file = BufferedInputFile(
            csv_data.encode("utf-8"),
            filename=f"users_{datetime.now().strftime('%Y%m%d')}.csv",
        )

        await callback.message.answer_document(
            document=file, caption=f"📥 Экспорт пользователей\n\nВсего: {len(users)}"
        )
        await callback.answer("✅ Файл отправлен")

    except Exception as e:
        logger.error(f"Export error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка экспорта", show_alert=True)
