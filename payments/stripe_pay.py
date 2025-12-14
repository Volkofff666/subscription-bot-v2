import stripe
from typing import Optional, Dict
import logging
from datetime import datetime
from config import STRIPE_SECRET_KEY, STRIPE_ENABLED, STRIPE_PRICE_ID, CHECKOUT_SUCCESS_URL, CHECKOUT_CANCEL_URL

logger = logging.getLogger(__name__)

if STRIPE_ENABLED and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


class StripePaymentHandler:
    @staticmethod
    async def create_subscription(user_id: int, username: Optional[str] = None) -> Optional[Dict]:
        if not STRIPE_ENABLED:
            logger.warning("Stripe отключен")
            return None
        
        if not STRIPE_PRICE_ID:
            logger.error("STRIPE_PRICE_ID не установлен")
            return None
        
        try:
            customer = stripe.Customer.create(
                metadata={'telegram_user_id': str(user_id), 'telegram_username': username or ''}
            )
            
            session = stripe.checkout.Session.create(
                customer=customer.id,
                payment_method_types=['card'],
                line_items=[{'price': STRIPE_PRICE_ID, 'quantity': 1}],
                mode='subscription',
                success_url=CHECKOUT_SUCCESS_URL,
                cancel_url=CHECKOUT_CANCEL_URL,
                client_reference_id=str(user_id),
                metadata={'telegram_user_id': str(user_id)},
                subscription_data={'metadata': {'telegram_user_id': str(user_id)}}
            )
            
            logger.info(f"✅ Stripe Session: {session.id} for user {user_id}")
            return {'session_url': session.url, 'session_id': session.id, 'customer_id': customer.id}
        except stripe.error.StripeError as e:
            logger.error(f"❌ Stripe error: {e}")
            return None
    
    @staticmethod
    async def cancel_subscription(stripe_subscription_id: str) -> bool:
        if not STRIPE_ENABLED:
            return False
        try:
            sub = stripe.Subscription.modify(stripe_subscription_id, cancel_at_period_end=True)
            logger.info(f"✅ Подписка отменена: {stripe_subscription_id}")
            return sub.cancel_at_period_end
        except stripe.error.StripeError as e:
            logger.error(f"❌ Ошибка отмены: {e}")
            return False
    
    @staticmethod
    def parse_webhook(payload: bytes, signature: str, webhook_secret: str) -> Optional[Dict]:
        try:
            return stripe.Webhook.construct_event(payload, signature, webhook_secret)
        except Exception as e:
            logger.error(f"❌ Webhook error: {e}")
            return None
