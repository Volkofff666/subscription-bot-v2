import pytest

from payments.factory import PaymentFactory
from payments.tribute_pay import TributePaymentHandler


@pytest.mark.asyncio
async def test_parse_webhook_new_donation_payload_format():
    data = {
        "name": "new_donation",
        "payload": {
            "telegram_user_id": 101,
            "amount": 19,
            "currency": "USD",
            "donation_request_id": "don_1",
            "message": "Thanks",
        },
    }
    result = await TributePaymentHandler.parse_webhook(data)
    assert result == {
        "user_id": 101,
        "amount": 19,
        "currency": "USD",
        "donation_id": "don_1",
        "message": "Thanks",
        "status": "succeeded",
    }


@pytest.mark.asyncio
async def test_parse_webhook_new_digital_product_data_format():
    data = {
        "name": "new_digital_product",
        "data": {
            "tg_user_id": 202,
            "amount": 25,
            "currency": "EUR",
            "product_id": "prod_77",
            "order_id": "order_9",
        },
    }
    result = await TributePaymentHandler.parse_webhook(data)
    assert result == {
        "user_id": 202,
        "amount": 25,
        "currency": "EUR",
        "donation_id": "prod_order_9",
        "message": "Product: prod_77",
        "status": "succeeded",
    }


@pytest.mark.asyncio
async def test_parse_webhook_unknown_event_returns_none():
    result = await TributePaymentHandler.parse_webhook({"name": "unknown_event"})
    assert result is None


@pytest.mark.asyncio
async def test_payment_factory_tribute_disabled_returns_none(monkeypatch):
    monkeypatch.setattr("payments.factory.TRIBUTE_ENABLED", False)
    result = await PaymentFactory.create_payment(123)
    assert result is None


@pytest.mark.asyncio
async def test_payment_factory_tribute_enabled_returns_link(monkeypatch):
    monkeypatch.setattr("payments.factory.TRIBUTE_ENABLED", True)

    async def fake_create_payment(user_id, username=None):
        assert user_id == 123
        assert username == "alice"
        return "https://t.me/tribute/app?startapp=test"

    monkeypatch.setattr(
        "payments.tribute_pay.TributePaymentHandler.create_payment",
        fake_create_payment,
    )

    result = await PaymentFactory.create_payment(123, "alice")
    assert result == "https://t.me/tribute/app?startapp=test"
