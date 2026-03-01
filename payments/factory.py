"""
Фабрика для создания платежей
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PaymentFactory:
    """Фабрика для выбора платежного провайдера"""

    @staticmethod
    async def create_payment(
        user_id: int, username: Optional[str] = None
    ) -> Optional[str]:
        """
        Создает платеж и возвращает URL для оплаты.

        Args:
            user_id: ID пользователя Telegram
            username: Username пользователя (опционально)

        Returns:
            URL для оплаты или None в случае ошибки
        """
        logger.info(f"💳 Using Stripe payment for user {user_id}")
        from .stripe_pay import StripePaymentHandler

        return await StripePaymentHandler.create_payment(user_id, username)

    @staticmethod
    def get_provider_name() -> str:
        return "Stripe"
