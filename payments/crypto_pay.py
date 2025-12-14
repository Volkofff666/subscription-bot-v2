import asyncio
from datetime import datetime
from typing import Optional
import logging
from config import CRYPTO_PAY_TOKEN, CRYPTO_PAY_ENABLED, SUBSCRIPTION_PRICE, SUBSCRIPTION_CURRENCY, FAKE_PAYMENT, FAKE_INVITE_LINK, FAKE_PAYMENT_DELAY

logger = logging.getLogger(__name__)

try:
    from aiocryptopay import AioCryptoPay, Networks
    CRYPTO_PAY_AVAILABLE = True
except ImportError:
    CRYPTO_PAY_AVAILABLE = False
    logger.warning("⚠️ aiocryptopay не установлен")


class CryptoPayHandler:
    def __init__(self):
        self.crypto = None
        if CRYPTO_PAY_AVAILABLE and CRYPTO_PAY_ENABLED and CRYPTO_PAY_TOKEN:
            try:
                self.crypto = AioCryptoPay(token=CRYPTO_PAY_TOKEN, network=Networks.MAIN_NET)
                logger.info("✅ CryptoPay инициализирован")
            except Exception as e:
                logger.error(f"❌ Ошибка CryptoPay: {e}")
    
    async def create_invoice(self, user_id: int) -> Optional[str]:
        if FAKE_PAYMENT:
            return f"https://fake-payment.com/pay?user_id={user_id}&amount={SUBSCRIPTION_PRICE}"
        
        if not self.crypto:
            logger.error("CryptoPay не инициализирован")
            return None
        
        try:
            invoice = await self.crypto.create_invoice(
                amount=SUBSCRIPTION_PRICE,
                asset=SUBSCRIPTION_CURRENCY,
                description=f"Подписка - User {user_id}",
                payload=f"subscription_{user_id}",
                expires_in=3600
            )
            logger.info(f"✅ CryptoPay invoice for user {user_id}")
            return invoice.bot_invoice_url
        except Exception as e:
            logger.error(f"❌ CryptoPay error: {e}")
            return None


async def simulate_payment_processing() -> bool:
    if FAKE_PAYMENT:
        logger.info(f"🧪 Симуляция платежа ({FAKE_PAYMENT_DELAY}s)...")
        await asyncio.sleep(FAKE_PAYMENT_DELAY)
        return True
    return False


def generate_fake_invite_link(user_id: int) -> str:
    timestamp = int(datetime.now().timestamp())
    return f"{FAKE_INVITE_LINK}?user={user_id}&time={timestamp}"
