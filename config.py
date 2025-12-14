"""
Конфигурация бота - все настройки из .env
"""
import os
from enum import Enum
from typing import List
from dotenv import load_dotenv

load_dotenv()


# ==================== TELEGRAM ====================
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
CHANNEL_ID: str = os.getenv("CHANNEL_ID", "")
ADMIN_IDS: List[int] = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
]


# ==================== STRIPE ====================
STRIPE_ENABLED: bool = os.getenv("STRIPE_ENABLED", "false").lower() == "true"
STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID: str = os.getenv("STRIPE_PRICE_ID", "")  # ID рекуррентной цены

CHECKOUT_SUCCESS_URL: str = os.getenv("CHECKOUT_SUCCESS_URL", "")
CHECKOUT_CANCEL_URL: str = os.getenv("CHECKOUT_CANCEL_URL", "")


# ==================== CRYPTOPAY ====================
CRYPTO_PAY_ENABLED: bool = os.getenv("CRYPTO_PAY_ENABLED", "false").lower() == "true"
CRYPTO_PAY_TOKEN: str = os.getenv("CRYPTO_PAY_TOKEN", "")


# ==================== SUBSCRIPTION ====================
SUBSCRIPTION_PRICE: float = float(os.getenv("SUBSCRIPTION_PRICE", "19"))
SUBSCRIPTION_CURRENCY: str = os.getenv("SUBSCRIPTION_CURRENCY", "USD")
SUBSCRIPTION_DAYS: int = int(os.getenv("SUBSCRIPTION_DAYS", "30"))


# ==================== SUPPORT ====================
SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "@support")
SUPPORT_USER_ID: int = int(os.getenv("SUPPORT_USER_ID", "0"))


# ==================== DATABASE ====================
DATABASE_PATH: str = "data/bot.db"


# ==================== TESTING ====================
FAKE_PAYMENT: bool = os.getenv("FAKE_PAYMENT", "false").lower() == "true"
FAKE_INVITE_LINK: str = os.getenv("FAKE_INVITE_LINK", "https://t.me/+TEST")
FAKE_PAYMENT_DELAY: int = int(os.getenv("FAKE_PAYMENT_DELAY", "2"))


# ==================== CONSTANTS ====================
MAX_CANCEL_REASON_LENGTH: int = 1000


class PaymentProvider(Enum):
    """Доступные платежные провайдеры"""
    STRIPE = "stripe"
    CRYPTO_PAY = "crypto_pay"
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
    
    if STRIPE_ENABLED and not all([STRIPE_SECRET_KEY, STRIPE_PRICE_ID, CHECKOUT_SUCCESS_URL, CHECKOUT_CANCEL_URL]):
        raise ValueError("Для Stripe нужны STRIPE_SECRET_KEY, STRIPE_PRICE_ID, CHECKOUT_SUCCESS_URL, CHECKOUT_CANCEL_URL")
    
    if CRYPTO_PAY_ENABLED and not CRYPTO_PAY_TOKEN:
        raise ValueError("Для CryptoPay нужен CRYPTO_PAY_TOKEN")
    
    if not FAKE_PAYMENT and not (STRIPE_ENABLED or CRYPTO_PAY_ENABLED):
        raise ValueError("Включите хотя бы один платежный провайдер или FAKE_PAYMENT")
    
    return True
