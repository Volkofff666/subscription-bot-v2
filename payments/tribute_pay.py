import hashlib
import hmac
import logging
from datetime import datetime
from typing import Dict, Optional

import aiohttp

from config import (
    SUBSCRIPTION_PRICE,
    TRIBUTE_API_KEY,
    TRIBUTE_ENABLED,
    TRIBUTE_PRODUCT_ID,
    TRIBUTE_WEBHOOK_SECRET,
)

logger = logging.getLogger(__name__)


class TributePaymentHandler:
    def __init__(self):
        self.api_key = TRIBUTE_API_KEY
        self.donation_link = TRIBUTE_PRODUCT_ID

    async def create_payment_link(
        self, user_id: int, username: Optional[str] = None
    ) -> Optional[str]:
        """Возвращает ссылку на страницу доната/продукта"""
        if not TRIBUTE_ENABLED:
            logger.warning("Tribute отключен")
            return None
        if not self.donation_link:
            logger.error("❌ TRIBUTE_PRODUCT_ID пустой, ссылка на оплату не задана")
            return None

        try:
            logger.info(
                f"✅ Tribute payment link for user {user_id}: {self.donation_link}"
            )
            return self.donation_link

        except Exception as e:
            logger.error(
                f"❌ Tribute error while creating payment link: {e}", exc_info=True
            )
            return None

    @staticmethod
    async def create_payment(user_id: int, username: Optional[str] = None) -> Optional[str]:
        """
        Совместимый entrypoint для PaymentFactory.
        Возвращает ссылку на оплату через экземпляр обработчика.
        """
        handler = TributePaymentHandler()
        return await handler.create_payment_link(user_id, username)

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str) -> bool:
        """Проверяет подпись webhook от Tribute"""
        # У Tribute нет webhook signature
        logger.info("✅ Tribute webhook accepted (no signature verification)")
        return True

    @staticmethod
    async def parse_webhook(data: Dict) -> Optional[Dict]:
        """Парсит webhook от Tribute о новом донате или покупке продукта"""
        try:
            event_name = data.get("name")
            logger.info(f"📨 Received webhook event: {event_name}")
            logger.info(f"   Raw data: {data}")

            # Обработка события "new_donation" (обычный донат)
            if event_name == "new_donation":
                # Поддержка обоих форматов: payload и data
                donation_data = data.get("payload") or data.get("data", {})

                # Поддержка обоих названий полей
                user_id = donation_data.get("telegram_user_id") or donation_data.get(
                    "tg_user_id"
                )
                amount = donation_data.get("amount")
                currency = donation_data.get("currency", "USD")
                donation_id = donation_data.get(
                    "donation_request_id"
                ) or donation_data.get("id")
                message = donation_data.get("message", "")

                logger.info(f"📩 New donation parsed successfully:")
                logger.info(f"   → User ID: {user_id}")
                logger.info(f"   → Amount: {amount} {currency}")
                logger.info(f"   → Donation ID: {donation_id}")

                return {
                    "user_id": user_id,
                    "amount": amount,
                    "currency": currency,
                    "donation_id": donation_id,
                    "message": message,
                    "status": "succeeded",
                }

            # Обработка события "new_digital_product" (покупка цифрового продукта)
            elif event_name == "new_digital_product":
                purchase_data = data.get("payload") or data.get("data", {})

                user_id = purchase_data.get("telegram_user_id") or purchase_data.get(
                    "tg_user_id"
                )
                amount = purchase_data.get("amount")
                currency = purchase_data.get("currency", "USD")
                product_id = purchase_data.get("product_id")
                order_id = purchase_data.get("order_id") or purchase_data.get("id")

                logger.info(f"🛒 Product purchase parsed successfully:")
                logger.info(f"   → User ID: {user_id}")
                logger.info(f"   → Amount: {amount} {currency}")
                logger.info(f"   → Product ID: {product_id}")
                logger.info(f"   → Order ID: {order_id}")

                return {
                    "user_id": user_id,
                    "amount": amount,
                    "currency": currency,
                    "donation_id": f"prod_{order_id}",
                    "message": f"Product: {product_id}",
                    "status": "succeeded",
                }

            else:
                logger.warning(f"⚠️ Unknown webhook event type: {event_name}")

            return None

        except Exception as e:
            logger.error(f"❌ Webhook parsing error: {e}", exc_info=True)
            logger.error(f"   Raw webhook data: {data}")
            return None
