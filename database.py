import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiosqlite

from config import DATABASE_PATH

logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db() -> None:
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    async with get_db() as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                has_payment_attempt BOOLEAN DEFAULT FALSE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                expires_at TIMESTAMP NOT NULL,
                invite_link TEXT,
                payment_provider TEXT,
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS cancellations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                reason TEXT NOT NULL,
                subscription_id TEXT,
                cancelled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscription_notifications (
                user_id INTEGER NOT NULL,
                notification_type TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, notification_type)
            )
        """)

        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_sub_stripe ON subscriptions(stripe_subscription_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_sub_expires ON subscriptions(expires_at)"
        )
        await db.commit()
        logger.info("✅ База данных инициализирована")


async def save_user(
    user_id: int, username: Optional[str] = None, first_name: Optional[str] = None
) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = COALESCE(excluded.username, username),
                first_name = COALESCE(excluded.first_name, first_name)
        """,
            (user_id, username or "", first_name or ""),
        )
        await db.commit()


async def mark_payment_attempt(user_id: int) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET has_payment_attempt = TRUE WHERE user_id = ?", (user_id,)
        )
        await db.commit()


async def has_payment_attempt(user_id: int) -> bool:
    async with get_db() as db:
        async with db.execute(
            "SELECT has_payment_attempt FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return bool(row and row[0]) if row else False


async def get_subscription(user_id: int) -> Optional[Dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "user_id": row["user_id"],
                    "expires_at": datetime.fromisoformat(row["expires_at"]),
                    "invite_link": row["invite_link"],
                    "payment_provider": row["payment_provider"],
                    "stripe_customer_id": row["stripe_customer_id"],
                    "stripe_subscription_id": row["stripe_subscription_id"],
                    "status": row["status"],
                }
            return None


async def is_subscription_active(user_id: int) -> bool:
    sub = await get_subscription(user_id)
    if not sub:
        return False
    return sub["status"] == "active" and sub["expires_at"] > datetime.now()


async def create_subscription(
    user_id: int,
    payment_provider: str,
    invite_link: str,
    days: int = 30,
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
) -> None:
    expires_at = datetime.now() + timedelta(days=days)
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO subscriptions
            (user_id, expires_at, invite_link, payment_provider, stripe_customer_id, stripe_subscription_id, status)
            VALUES (?, ?, ?, ?, ?, ?, 'active')
            ON CONFLICT(user_id) DO UPDATE SET
                expires_at=excluded.expires_at,
                invite_link=excluded.invite_link,
                stripe_customer_id=excluded.stripe_customer_id,
                stripe_subscription_id=excluded.stripe_subscription_id,
                status='active'
        """,
            (
                user_id,
                expires_at.isoformat(),
                invite_link,
                payment_provider,
                stripe_customer_id,
                stripe_subscription_id,
            ),
        )
        await db.execute(
            "DELETE FROM subscription_notifications WHERE user_id = ?", (user_id,)
        )
        await db.commit()


async def update_subscription_period(user_id: int, new_expires_at: datetime) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE subscriptions SET expires_at = ?, status = 'active' WHERE user_id = ?",
            (new_expires_at.isoformat(), user_id),
        )
        await db.commit()


async def cancel_subscription(user_id: int) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE subscriptions SET status = 'cancelled' WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


async def expire_subscription(user_id: int) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE subscriptions SET status = 'expired' WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


async def save_cancellation_reason(
    user_id: int,
    username: Optional[str],
    reason: str,
    subscription_id: Optional[str] = None,
) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO cancellations (user_id, username, reason, subscription_id) VALUES (?, ?, ?, ?)",
            (user_id, username or "", reason, subscription_id),
        )
        await db.commit()


async def get_subscription_by_stripe_id(stripe_subscription_id: str) -> Optional[Dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM subscriptions WHERE stripe_subscription_id = ?",
            (stripe_subscription_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"user_id": row["user_id"], "status": row["status"]}
            return None


async def get_user_stats() -> str:
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            total_users = (await cursor.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE status = 'active' AND expires_at > ?",
            (datetime.now().isoformat(),),
        ) as cursor:
            active_subs = (await cursor.fetchone())[0]
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        async with db.execute(
            "SELECT COUNT(*) FROM cancellations WHERE cancelled_at > ?", (week_ago,)
        ) as cursor:
            cancellations = (await cursor.fetchone())[0]

        return f"👥 Всего пользователей: {total_users}\n💎 Активных подписок: {active_subs}\n❌ Отмен за 7 дней: {cancellations}"


async def get_all_users() -> List[Dict]:
    async with get_db() as db:
        async with db.execute("SELECT user_id, username FROM users") as cursor:
            return [
                {"user_id": row[0], "username": row[1]}
                for row in await cursor.fetchall()
            ]

            async def get_all_users() -> List[Dict]:
                async with get_db() as db:
                    async with db.execute(
                        "SELECT user_id, username, first_name FROM users"
                    ) as cursor:
                        return [
                            {
                                "user_id": row[0],
                                "username": row[1],
                                "first_name": row[2],
                            }
                            for row in await cursor.fetchall()
                        ]


async def get_expiring_subscriptions(days: int = 3) -> List[Dict]:
    """Подписки, истекающие в ближайшие N дней, которым еще не отправлено уведомление."""
    now = datetime.now()
    limit = now + timedelta(days=days)
    async with get_db() as db:
        async with db.execute(
            """
            SELECT s.user_id, s.expires_at
            FROM subscriptions s
            WHERE s.status = 'active'
              AND s.expires_at > ?
              AND s.expires_at <= ?
              AND NOT EXISTS (
                  SELECT 1 FROM subscription_notifications n
                  WHERE n.user_id = s.user_id
                    AND n.notification_type = ?
              )
            """,
            (now.isoformat(), limit.isoformat(), f"expiry_{days}d"),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {"user_id": row[0], "expires_at": datetime.fromisoformat(row[1])}
                for row in rows
            ]


async def mark_notification(user_id: int, notification_type: str) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO subscription_notifications (user_id, notification_type)
            VALUES (?, ?)
            """,
            (user_id, notification_type),
        )
        await db.commit()


async def get_expired_active_subscriptions() -> List[Dict]:
    """Активные подписки, у которых истек срок."""
    now = datetime.now()
    async with get_db() as db:
        async with db.execute(
            """
            SELECT user_id, expires_at
            FROM subscriptions
            WHERE status = 'active' AND expires_at <= ?
            """,
            (now.isoformat(),),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {"user_id": row[0], "expires_at": datetime.fromisoformat(row[1])}
                for row in rows
            ]
