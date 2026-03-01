"""
Фоновые задачи по подпискам: предупреждение за 3 дня и исключение после окончания.
Ежедневный бекап базы данных.
"""

import asyncio
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from aiogram import Bot

from config import CHANNEL_ID, DATABASE_PATH, SUBSCRIPTION_CHECK_HOUR, SUBSCRIPTION_CHECK_TZ_OFFSET
from database import (
    expire_subscription,
    get_expired_active_subscriptions,
    get_expiring_subscriptions,
    mark_notification,
)
from keyboards import renewal_offer_keyboard, subscription_offer_keyboard
from messages import format_message
from payments import PaymentFactory

logger = logging.getLogger(__name__)

WARNING_DAYS = (3, 1)
BACKUP_KEEP_COUNT = 7


async def backup_database() -> Optional[Path]:
    """
    Создаёт бекап базы данных с временной меткой.
    Хранит последние BACKUP_KEEP_COUNT копий, более старые удаляет.
    Возвращает путь к созданному файлу или None при ошибке.
    """
    db_path = Path(DATABASE_PATH)
    if not db_path.exists():
        logger.warning("⚠️ Файл БД не найден, бекап пропущен: %s", db_path)
        return None

    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"bot_{timestamp}.db"

    try:
        shutil.copy2(db_path, backup_path)
        logger.info("✅ Бекап создан: %s", backup_path)
    except OSError as e:
        logger.error("❌ Ошибка создания бекапа: %s", e)
        return None

    # Удаляем старые бекапы, оставляем последние BACKUP_KEEP_COUNT
    backups = sorted(backup_dir.glob("bot_*.db"))
    for old in backups[:-BACKUP_KEEP_COUNT]:
        try:
            old.unlink()
            logger.info("🗑 Старый бекап удалён: %s", old)
        except OSError:
            pass

    return backup_path


async def _send_expiry_warnings(bot: Bot) -> None:
    for warning_days in WARNING_DAYS:
        expiring = await get_expiring_subscriptions(days=warning_days)
        if not expiring:
            continue

        for item in expiring:
            user_id = item["user_id"]
            expires_at = item["expires_at"]
            days_left = max((expires_at - datetime.now()).days, 0)

            try:
                payment_url = await PaymentFactory.create_payment(user_id)
            except Exception as e:
                logger.warning(f"Failed to create payment URL for {user_id}: {e}")
                payment_url = None

            text = format_message("subscription_expiring_soon", days_left=days_left)
            if payment_url:
                text += f'\n💳 <a href="{payment_url}">Продлить подписку</a>'
            keyboard = renewal_offer_keyboard() if payment_url else None

            try:
                await bot.send_message(
                    user_id,
                    text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
                await mark_notification(user_id, f"expiry_{warning_days}d")
                logger.info("Sent expiry warning (%sd) to %s", warning_days, user_id)
            except Exception as e:
                logger.warning(f"Failed to send expiry warning to {user_id}: {e}")


async def _revoke_expired(bot: Bot) -> None:
    expired = await get_expired_active_subscriptions()
    if not expired:
        return

    for item in expired:
        user_id = item["user_id"]
        try:
            # Исключаем пользователя из канала; сразу снимаем бан,
            # чтобы он мог вернуться после оплаты
            await bot.ban_chat_member(chat_id=int(CHANNEL_ID), user_id=user_id)
            await bot.unban_chat_member(chat_id=int(CHANNEL_ID), user_id=user_id)
            logger.info(f"Kicked expired user {user_id} from channel")
        except Exception as e:
            logger.warning(f"Failed to kick user {user_id}: {e}")

        try:
            await expire_subscription(user_id)
        except Exception as e:
            logger.warning(f"Failed to expire subscription for {user_id}: {e}")

        try:
            payment_url = await PaymentFactory.create_payment(user_id)
        except Exception as e:
            logger.warning(f"Failed to create payment URL for {user_id}: {e}")
            payment_url = None

        text = format_message("subscription_expired")
        if payment_url:
            text += f'\n💳 <a href="{payment_url}">Оформить подписку снова</a>'
        keyboard = renewal_offer_keyboard() if payment_url else subscription_offer_keyboard()

        try:
            await bot.send_message(
                user_id,
                text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
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
            await backup_database()
        except Exception as e:
            logger.error(f"Subscription task error: {e}", exc_info=True)
