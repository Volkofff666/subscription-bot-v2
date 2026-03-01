import json

import pytest

import payments.stripe_pay as stripe_module
from payments.factory import PaymentFactory
from payments.stripe_pay import StripePaymentHandler


def _make_payload(event_type: str, session_obj: dict) -> bytes:
    return json.dumps({"type": event_type, "data": {"object": session_obj}}).encode()


@pytest.fixture(autouse=True)
def disable_stripe_signature(monkeypatch):
    """Отключаем проверку подписи webhook для всех тестов."""
    monkeypatch.setattr(stripe_module, "STRIPE_WEBHOOK_SECRET", "")


def test_parse_stripe_webhook_checkout_completed():
    payload = _make_payload(
        "checkout.session.completed",
        {
            "id": "cs_test_abc123",
            "amount_total": 1900,
            "currency": "usd",
            "metadata": {"telegram_user_id": "42"},
        },
    )
    result = StripePaymentHandler.parse_webhook(payload, "")

    assert result is not None
    assert result["user_id"] == 42
    assert result["amount"] == 19.0
    assert result["currency"] == "USD"
    assert result["session_id"] == "cs_test_abc123"
    assert result["status"] == "succeeded"


def test_parse_stripe_webhook_unknown_event_returns_none():
    payload = _make_payload("payment_intent.created", {"id": "pi_test"})
    result = StripePaymentHandler.parse_webhook(payload, "")
    assert result is None


def test_parse_stripe_webhook_missing_user_id_returns_none():
    payload = _make_payload(
        "checkout.session.completed",
        {
            "id": "cs_test_xyz",
            "amount_total": 1900,
            "currency": "usd",
            "metadata": {},  # нет telegram_user_id
        },
    )
    result = StripePaymentHandler.parse_webhook(payload, "")
    assert result is None


@pytest.mark.asyncio
async def test_payment_factory_returns_stripe_url(monkeypatch):
    async def fake_create(user_id, username=None):
        return "https://checkout.stripe.com/pay/cs_test_abc"

    monkeypatch.setattr(StripePaymentHandler, "create_payment", fake_create)

    result = await PaymentFactory.create_payment(123, "alice")
    assert result == "https://checkout.stripe.com/pay/cs_test_abc"


@pytest.mark.asyncio
async def test_payment_factory_on_stripe_error_returns_none(monkeypatch):
    async def failing_create(user_id, username=None):
        return None

    monkeypatch.setattr(StripePaymentHandler, "create_payment", failing_create)

    result = await PaymentFactory.create_payment(999)
    assert result is None
