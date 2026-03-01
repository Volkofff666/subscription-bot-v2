"""
Stripe Checkout payment handler
"""

import logging
from typing import Dict, Optional

import stripe

from config import (
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
    STRIPE_PRICE_ID,
    STRIPE_SUCCESS_URL,
    STRIPE_CANCEL_URL,
    SUBSCRIPTION_PRICE,
    SUBSCRIPTION_CURRENCY,
)

logger = logging.getLogger(__name__)

stripe.api_key = STRIPE_SECRET_KEY


class StripePaymentHandler:

    @staticmethod
    async def create_payment(user_id: int, username: Optional[str] = None) -> Optional[str]:
        """Создает Stripe Checkout Session и возвращает URL для оплаты."""
        if not STRIPE_PRICE_ID:
            logger.error("❌ STRIPE_PRICE_ID не задан")
            return None

        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
                metadata={"telegram_user_id": str(user_id)},
                subscription_data={"metadata": {"telegram_user_id": str(user_id)}},
                success_url=STRIPE_SUCCESS_URL,
                cancel_url=STRIPE_CANCEL_URL,
            )
            logger.info(f"✅ Stripe Checkout Session создан для user {user_id}: {session.id}")
            return session.url

        except stripe.StripeError as e:
            logger.error(f"❌ Stripe error for user {user_id}: {e}", exc_info=True)
            return None

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str) -> bool:
        """Проверяет подпись Stripe webhook."""
        if not STRIPE_WEBHOOK_SECRET:
            logger.warning("⚠️ STRIPE_WEBHOOK_SECRET не задан, проверка подписи пропущена")
            return True
        try:
            stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
            return True
        except stripe.SignatureVerificationError:
            logger.warning("⛔ Неверная подпись Stripe webhook")
            return False

    @staticmethod
    def parse_webhook(payload: bytes, signature: str) -> Optional[Dict]:
        """
        Парсит Stripe webhook и возвращает данные платежа при успешной оплате.
        Обрабатывает событие checkout.session.completed.
        """
        try:
            if STRIPE_WEBHOOK_SECRET:
                event = stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
            else:
                import json
                event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)

            logger.info(f"📨 Stripe event: {event['type']}")

            if event["type"] == "checkout.session.completed":
                session = event["data"]["object"]
                metadata = session.get("metadata", {})
                user_id_str = metadata.get("telegram_user_id")

                if not user_id_str:
                    logger.error("❌ telegram_user_id отсутствует в metadata Stripe session")
                    return None

                amount_total = session.get("amount_total", 0)
                currency = session.get("currency", SUBSCRIPTION_CURRENCY).upper()
                # For subscription mode, store the Stripe Subscription ID (sub_...)
                stripe_sub_id = session.get("subscription") or session.get("id", "")

                return {
                    "user_id": int(user_id_str),
                    "amount": amount_total / 100,
                    "currency": currency,
                    "session_id": stripe_sub_id,
                    "status": "succeeded",
                }

            if event["type"] == "invoice.payment_succeeded":
                invoice = event["data"]["object"]
                # Only handle recurring renewals, not the first invoice (covered by checkout.session.completed)
                if invoice.get("billing_reason") != "subscription_cycle":
                    return None

                subscription_id = invoice.get("subscription")
                if not subscription_id:
                    return None

                stripe_sub = stripe.Subscription.retrieve(subscription_id)
                user_id_str = stripe_sub.metadata.get("telegram_user_id")

                if not user_id_str:
                    logger.error(f"❌ telegram_user_id отсутствует в metadata подписки {subscription_id}")
                    return None

                return {
                    "user_id": int(user_id_str),
                    "amount": invoice.get("amount_paid", 0) / 100,
                    "currency": invoice.get("currency", SUBSCRIPTION_CURRENCY).upper(),
                    "session_id": subscription_id,
                    "status": "renewed",
                }

            return None

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга Stripe webhook: {e}", exc_info=True)
            return None
