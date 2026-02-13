"""
Фоновые задачи по подпискам: предупреждение за 3 дня и исключение после окончания.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from config import CHANNEL_ID, SUBSCRIPTION_CHECK_HOUR, SUBSCRIPTION_CHECK_TZ_OFFSET
from database import (
    expire_subscription,
    get_expired_active_subscriptions,
    get_expiring_subscriptions,
    mark_notification,
)
from messages import format_message

logger = logging.getLogger(__name__)


WARNING_DAYS = 3


async def _send_expiry_warnings(bot: Bot) -> None:
    expiring = await get_expiring_subscriptions(days=WARNING_DAYS)
    if not expiring:
        return

    for item in expiring:
        user_id = item["user_id"]
        expires_at = item["expires_at"]
        days_left = max((expires_at - datetime.now()).days, 0)

        try:
            await bot.send_message(
                user_id,
                format_message("subscription_expiring_soon", days_left=days_left),
            )
            await mark_notification(user_id, f"expiry_{WARNING_DAYS}d")
            logger.info(f"Sent expiry warning to {user_id}")
        except Exception as e:
            logger.warning(f"Failed to send expiry warning to {user_id}: {e}")


async def _revoke_expired(bot: Bot) -> None:
    expired = await get_expired_active_subscriptions()
    if not expired:
        return

    for item in expired:
        user_id = item["user_id"]
        try:
            # Исключаем пользователя из группы/канала
            await bot.ban_chat_member(chat_id=int(CHANNEL_ID), user_id=user_id)
            # Сразу снимаем бан, чтобы пользователь мог вернуться после оплаты
            await bot.unban_chat_member(chat_id=int(CHANNEL_ID), user_id=user_id)
        except Exception as e:
            logger.warning(f"Failed to kick user {user_id}: {e}")

        try:
            await expire_subscription(user_id)
        except Exception as e:
            logger.warning(f"Failed to expire subscription for {user_id}: {e}")

        try:
            await bot.send_message(user_id, format_message("subscription_expired"))
        except Exception as e:
            logger.warning(f"Failed to notify user {user_id} about expiration: {e}")


def _seconds_until_next_check(now: datetime) -> int:
    next_check = now.replace(
        hour=SUBSCRIPTION_CHECK_HOUR, minute=0, second=0, microsecond=0
    )
    if next_check <= now:
        next_check = next_check + timedelta(days=1)
    return int((next_check - now).total_seconds())


async def subscription_enforcer(bot: Bot) -> None:
    """Проверяет подписки раз в сутки в заданный час."""
    tz = timezone(timedelta(hours=SUBSCRIPTION_CHECK_TZ_OFFSET))
    logger.info(
        "🔄 Мониторинг подписок: ежедневно в %02d:00 (UTC%+d)",
        SUBSCRIPTION_CHECK_HOUR,
        SUBSCRIPTION_CHECK_TZ_OFFSET,
    )
    while True:
        delay = _seconds_until_next_check(datetime.now(tz))
        await asyncio.sleep(delay)

        try:
            await _send_expiry_warnings(bot)
            await _revoke_expired(bot)
        except Exception as e:
            logger.error(f"Subscription task error: {e}", exc_info=True)
