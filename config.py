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
WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "/webhook/stripe")

# ==================== STRIPE ====================
STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID: str = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_SUCCESS_URL: str = os.getenv("STRIPE_SUCCESS_URL", "https://t.me/")
STRIPE_CANCEL_URL: str = os.getenv("STRIPE_CANCEL_URL", "https://t.me/")

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

    STRIPE = "stripe"
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

    if not STRIPE_SECRET_KEY:
        logger.warning("⚠️ STRIPE_SECRET_KEY не установлен, платежи не будут работать")
    if not STRIPE_PRICE_ID:
        logger.warning("⚠️ STRIPE_PRICE_ID не установлен, платежи не будут работать")
    if not STRIPE_WEBHOOK_SECRET:
        logger.warning("⚠️ STRIPE_WEBHOOK_SECRET не установлен, подпись webhook не проверяется")

    if SUBSCRIPTION_CHECK_HOUR < 0 or SUBSCRIPTION_CHECK_HOUR > 23:
        raise ValueError("SUBSCRIPTION_CHECK_HOUR должен быть в диапазоне 0-23")
    if SUBSCRIPTION_CHECK_TZ_OFFSET < -23 or SUBSCRIPTION_CHECK_TZ_OFFSET > 23:
        raise ValueError("SUBSCRIPTION_CHECK_TZ_OFFSET должен быть в диапазоне -23..23")

    logger.info("✅ Конфигурация загружена:")
    logger.info(f"   - Stripe: {'✅' if STRIPE_SECRET_KEY else '❌'}")
    logger.info(f"   - Админов: {len(ADMIN_IDS)}")
    logger.info(f"   - Webhook: {WEBHOOK_HOST}:{WEBHOOK_PORT}{WEBHOOK_PATH}")

    return True
