from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_keyboard_new_user() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Приобрести подписку", callback_data="subscribe")]
    ])


def main_keyboard_after_payment_attempt() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Приобрести подписку", callback_data="subscribe")],
        [InlineKeyboardButton(text="❓ Поддержка", callback_data="support")]
    ])


def main_keyboard_subscribed() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Мой статус", callback_data="status")],
        [InlineKeyboardButton(text="❓ Поддержка", callback_data="support")]
    ])


def subscription_offer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", callback_data="pay_now")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])


def payment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])


def status_keyboard_active() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить подписку", callback_data="cancel_subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])


def cancel_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, отменить", callback_data="cancel_confirm_yes")],
        [InlineKeyboardButton(text="❌ Нет, оставить", callback_data="cancel_confirm_no")]
    ])


def support_keyboard(support_username: str) -> InlineKeyboardMarkup:
    username = support_username.lstrip('@')
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать в поддержку", url=f"https://t.me/{username}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])


def back_to_status_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к статусу", callback_data="status")]
    ])


def renewal_offer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отказаться от продления", callback_data="renewal_decline")]
    ])
