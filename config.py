"""
Конфигурация бота - все настройки из .env
"""

import logging
import os
from enum import Enum
from typing import List

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ==================== TELEGRAM ====================
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
CHANNEL_ID: str = os.getenv("CHANNEL_ID", "")
ADMIN_IDS: List[int] = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
]
WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "9443"))
WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "/webhook/tribute")

# ==================== TRIBUTE ====================
TRIBUTE_ENABLED: bool = os.getenv("TRIBUTE_ENABLED", "true").lower() == "true"
TRIBUTE_API_KEY: str = os.getenv("TRIBUTE_API_KEY", "")
TRIBUTE_WEBHOOK_SECRET: str = os.getenv("TRIBUTE_WEBHOOK_SECRET", "")
TRIBUTE_PRODUCT_ID: str = os.getenv("TRIBUTE_PRODUCT_ID", "")
TRIBUTE_SUBSCRIPTION_URL: str = os.getenv(
    "TRIBUTE_SUBSCRIPTION_URL", "https://t.me/tribute/app?startapp=sOFz"
)

# ==================== SUBSCRIPTION ====================
SUBSCRIPTION_PRICE: float = float(os.getenv("SUBSCRIPTION_PRICE", "19"))
SUBSCRIPTION_CURRENCY: str = os.getenv("SUBSCRIPTION_CURRENCY", "USD")
SUBSCRIPTION_DAYS: int = int(os.getenv("SUBSCRIPTION_DAYS", "30"))
SUBSCRIPTION_CHECK_HOUR: int = int(os.getenv("SUBSCRIPTION_CHECK_HOUR", "12"))
SUBSCRIPTION_CHECK_TZ_OFFSET: int = int(
    os.getenv("SUBSCRIPTION_CHECK_TZ_OFFSET", "0")
)

# ==================== SUPPORT ====================
SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "@support")
SUPPORT_USER_ID: int = int(os.getenv("SUPPORT_USER_ID", "0"))

# ==================== DATABASE ====================
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/bot.db")

# ==================== SSL ====================
SSL_CERT_PATH: str = os.getenv(
    "SSL_CERT_PATH", "/etc/letsencrypt/live/de01.nocto.online/fullchain.pem"
)
SSL_KEY_PATH: str = os.getenv(
    "SSL_KEY_PATH", "/etc/letsencrypt/live/de01.nocto.online/privkey.pem"
)

# ==================== CONSTANTS ====================
MAX_CANCEL_REASON_LENGTH: int = 1000


class PaymentProvider(Enum):
    """Доступные платежные провайдеры"""

    TRIBUTE = "tribute"
    FAKE = "fake"


class SubscriptionStatus(Enum):
    """Статусы подписки"""

    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


def validate_config() -> bool:
    """Проверка корректности конфигурации"""
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не установлен в .env")

    if not CHANNEL_ID:
        raise ValueError("CHANNEL_ID не установлен в .env")

    if WEBHOOK_PORT < 1 or WEBHOOK_PORT > 65535:
        raise ValueError("WEBHOOK_PORT должен быть в диапазоне 1..65535")
    if not WEBHOOK_PATH.startswith("/"):
        raise ValueError("WEBHOOK_PATH должен начинаться с /")

    if not ADMIN_IDS:
        logger.warning(
            "⚠️ ADMIN_IDS не установлены, команды администратора будут недоступны"
        )

    if TRIBUTE_ENABLED and not TRIBUTE_API_KEY:
        logger.warning("⚠️ TRIBUTE_API_KEY не установлен, платежи могут не работать")
    if TRIBUTE_ENABLED and not TRIBUTE_SUBSCRIPTION_URL:
        logger.warning(
            "⚠️ TRIBUTE_SUBSCRIPTION_URL не установлен, ссылка оплаты будет пустой"
        )

    if not TRIBUTE_ENABLED:
        raise ValueError("Включите TRIBUTE_ENABLED=true для приема платежей")

    if SUBSCRIPTION_CHECK_HOUR < 0 or SUBSCRIPTION_CHECK_HOUR > 23:
        raise ValueError("SUBSCRIPTION_CHECK_HOUR должен быть в диапазоне 0-23")
    if SUBSCRIPTION_CHECK_TZ_OFFSET < -23 or SUBSCRIPTION_CHECK_TZ_OFFSET > 23:
        raise ValueError("SUBSCRIPTION_CHECK_TZ_OFFSET должен быть в диапазоне -23..23")

    logger.info(f"✅ Конфигурация загружена:")
    logger.info(f"   - Tribute: {'✅' if TRIBUTE_ENABLED else '❌'}")
    logger.info(f"   - Админов: {len(ADMIN_IDS)}")
    logger.info(f"   - Webhook: {WEBHOOK_HOST}:{WEBHOOK_PORT}{WEBHOOK_PATH}")

    return True
