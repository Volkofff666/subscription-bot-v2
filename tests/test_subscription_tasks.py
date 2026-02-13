from datetime import datetime, timedelta, timezone

import pytest

import subscription_tasks


class FakeBot:
    def __init__(self):
        self.messages = []
        self.bans = []
        self.unbans = []

    async def send_message(self, user_id, text):
        self.messages.append((user_id, text))

    async def ban_chat_member(self, chat_id, user_id):
        self.bans.append((chat_id, user_id))

    async def unban_chat_member(self, chat_id, user_id):
        self.unbans.append((chat_id, user_id))


@pytest.mark.asyncio
async def test_send_expiry_warnings_marks_notification(monkeypatch):
    bot = FakeBot()
    now = datetime.now()
    marked = []

    async def fake_get_expiring_subscriptions(days):
        assert days == subscription_tasks.WARNING_DAYS
        return [{"user_id": 10, "expires_at": now + timedelta(days=2)}]

    async def fake_mark_notification(user_id, notification_type):
        marked.append((user_id, notification_type))

    monkeypatch.setattr(
        subscription_tasks, "get_expiring_subscriptions", fake_get_expiring_subscriptions
    )
    monkeypatch.setattr(subscription_tasks, "mark_notification", fake_mark_notification)

    await subscription_tasks._send_expiry_warnings(bot)

    assert len(bot.messages) == 1
    assert bot.messages[0][0] == 10
    assert "Подписка скоро истекает" in bot.messages[0][1]
    assert marked == [(10, "expiry_3d")]


@pytest.mark.asyncio
async def test_revoke_expired_bans_unbans_expires_and_notifies(monkeypatch):
    bot = FakeBot()
    expired_called = []

    async def fake_get_expired_active_subscriptions():
        return [{"user_id": 22, "expires_at": datetime.now() - timedelta(days=1)}]

    async def fake_expire_subscription(user_id):
        expired_called.append(user_id)

    monkeypatch.setattr(
        subscription_tasks, "get_expired_active_subscriptions", fake_get_expired_active_subscriptions
    )
    monkeypatch.setattr(subscription_tasks, "expire_subscription", fake_expire_subscription)
    monkeypatch.setattr(subscription_tasks, "CHANNEL_ID", "123456")

    await subscription_tasks._revoke_expired(bot)

    assert bot.bans == [(123456, 22)]
    assert bot.unbans == [(123456, 22)]
    assert expired_called == [22]
    assert bot.messages == [(22, subscription_tasks.format_message("subscription_expired"))]


def test_seconds_until_next_check_before_hour(monkeypatch):
    monkeypatch.setattr(subscription_tasks, "SUBSCRIPTION_CHECK_HOUR", 12)
    now = datetime(2026, 1, 1, 10, 30, 0, tzinfo=timezone.utc)
    assert subscription_tasks._seconds_until_next_check(now) == 5400


def test_seconds_until_next_check_after_hour(monkeypatch):
    monkeypatch.setattr(subscription_tasks, "SUBSCRIPTION_CHECK_HOUR", 12)
    now = datetime(2026, 1, 1, 12, 30, 0, tzinfo=timezone.utc)
    assert subscription_tasks._seconds_until_next_check(now) == 84600
