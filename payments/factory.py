from typing import Optional
import logging
from config import STRIPE_ENABLED, CRYPTO_PAY_ENABLED, FAKE_PAYMENT, PaymentProvider
from .stripe_pay import StripePaymentHandler
from .crypto_pay import CryptoPayHandler

logger = logging.getLogger(__name__)


class PaymentFactory:
    @staticmethod
    def get_provider() -> PaymentProvider:
        if FAKE_PAYMENT:
            return PaymentProvider.FAKE
        elif STRIPE_ENABLED:
            return PaymentProvider.STRIPE
        elif CRYPTO_PAY_ENABLED:
            return PaymentProvider.CRYPTO_PAY
        else:
            logger.warning("⚠️ Нет активных провайдеров, используется FAKE")
            return PaymentProvider.FAKE
    
    @staticmethod
    async def create_payment(user_id: int, username: Optional[str] = None) -> Optional[str]:
        provider = PaymentFactory.get_provider()
        
        if provider == PaymentProvider.STRIPE:
            logger.info(f"💳 Создание Stripe подписки для user {user_id}")
            handler = StripePaymentHandler()
            result = await handler.create_subscription(user_id, username)
            return result['session_url'] if result else None
        
        elif provider == PaymentProvider.CRYPTO_PAY:
            logger.info(f"🪙 Создание CryptoPay платежа для user {user_id}")
            handler = CryptoPayHandler()
            return await handler.create_invoice(user_id)
        
        else:
            logger.info(f"🧪 Фейковый платеж для user {user_id}")
            return f"https://fake-payment.com/pay?user_id={user_id}"
    
    @staticmethod
    def get_provider_name() -> str:
        provider = PaymentFactory.get_provider()
        names = {
            PaymentProvider.STRIPE: "Stripe (рекуррентная подписка)",
            PaymentProvider.CRYPTO_PAY: "CryptoPay (криптовалюта)",
            PaymentProvider.FAKE: "Тестовый режим"
        }
        return names.get(provider, "Неизвестно")
