from datetime import datetime, timedelta

import pytest

import database


@pytest.mark.asyncio
async def test_user_lifecycle_and_payment_attempt():
    await database.init_db()
    await database.save_user(1001, "alice", "Alice")

    users = await database.get_all_users()
    assert users == [{"user_id": 1001, "username": "alice"}]

    assert await database.has_payment_attempt(1001) is False
    await database.mark_payment_attempt(1001)
    assert await database.has_payment_attempt(1001) is True


@pytest.mark.asyncio
async def test_subscription_create_activate_cancel_and_expire():
    await database.init_db()
    await database.save_user(2002, "bob", "Bob")

    await database.create_subscription(
        user_id=2002,
        payment_provider="tribute",
        invite_link="https://t.me/+invite",
        days=10,
        stripe_subscription_id="tr_abc123",
    )

    sub = await database.get_subscription(2002)
    assert sub is not None
    assert sub["status"] == "active"
    assert sub["payment_provider"] == "tribute"
    assert sub["stripe_subscription_id"] == "tr_abc123"
    assert sub["expires_at"] > datetime.now()
    assert await database.is_subscription_active(2002) is True

    by_stripe = await database.get_subscription_by_stripe_id("tr_abc123")
    assert by_stripe == {"user_id": 2002, "status": "active"}

    await database.cancel_subscription(2002)
    cancelled = await database.get_subscription(2002)
    assert cancelled["status"] == "cancelled"
    assert await database.is_subscription_active(2002) is False

    await database.expire_subscription(2002)
    expired = await database.get_subscription(2002)
    assert expired["status"] == "expired"


@pytest.mark.asyncio
async def test_notification_and_expiring_queries():
    await database.init_db()
    await database.save_user(3003, "charlie", "Charlie")
    await database.create_subscription(
        user_id=3003,
        payment_provider="tribute",
        invite_link="https://t.me/+invite2",
        days=2,
        stripe_subscription_id="tr_short",
    )

    expiring = await database.get_expiring_subscriptions(days=3)
    user_ids = {item["user_id"] for item in expiring}
    assert 3003 in user_ids

    await database.mark_notification(3003, "expiry_3d")
    expiring_after_mark = await database.get_expiring_subscriptions(days=3)
    user_ids_after = {item["user_id"] for item in expiring_after_mark}
    assert 3003 not in user_ids_after


@pytest.mark.asyncio
async def test_expired_active_subscriptions_query_and_stats():
    await database.init_db()
    await database.save_user(4004, "dora", "Dora")
    await database.create_subscription(
        user_id=4004,
        payment_provider="tribute",
        invite_link="https://t.me/+invite3",
        days=30,
    )

    past = datetime.now() - timedelta(days=1)
    await database.update_subscription_period(4004, past)

    expired = await database.get_expired_active_subscriptions()
    expired_ids = {item["user_id"] for item in expired}
    assert 4004 in expired_ids

    await database.save_cancellation_reason(4004, "dora", "Too expensive")
    stats = await database.get_user_stats()
    assert "Всего пользователей: 1" in stats
    assert "Отмен за 7 дней: 1" in stats
