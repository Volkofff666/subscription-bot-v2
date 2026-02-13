"""
Фабрика для создания платежей
"""

import logging
from typing import Optional

from config import TRIBUTE_API_KEY, TRIBUTE_ENABLED

logger = logging.getLogger(__name__)


class PaymentFactory:
    """Фабрика для выбора платежного провайдера"""

    @staticmethod
    async def create_payment(
        user_id: int, username: Optional[str] = None
    ) -> Optional[str]:
        """
        Создает платеж и возвращает URL для оплаты

        Args:
            user_id: ID пользователя Telegram
            username: Username пользователя (опционально)

        Returns:
            URL для оплаты или None в случае ошибки
        """

        if TRIBUTE_ENABLED:
            logger.info(f"💳 Using TRIBUTE payment for user {user_id}")
            from .tribute_pay import TributePaymentHandler

            return await TributePaymentHandler.create_payment(user_id, username)

        logger.error("❌ No payment provider enabled!")
        return None

    @staticmethod
    def get_provider_name() -> str:
        """Возвращает название активного провайдера"""
        if TRIBUTE_ENABLED:
            return "Tribute"
        return "None"
