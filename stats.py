#!/usr/bin/env python3
import sqlite3
from datetime import datetime, timedelta

DB_PATH = "/root/subscription-bot-v2/data/bot.db"


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Общая статистика
    total_users = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    active_subs = cursor.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE status = 'active' AND expires_at > datetime('now')"
    ).fetchone()[0]
    cancelled_subs = cursor.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE status = 'cancelled'"
    ).fetchone()[0]

    # Периоды
    now = datetime.now()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    day_users = cursor.execute(
        "SELECT COUNT(*) FROM users WHERE join_date > ?", (day_ago,)
    ).fetchone()[0]

    week_users = cursor.execute(
        "SELECT COUNT(*) FROM users WHERE join_date > ?", (week_ago,)
    ).fetchone()[0]

    month_users = cursor.execute(
        "SELECT COUNT(*) FROM users WHERE join_date > ?", (month_ago,)
    ).fetchone()[0]

    # Платежи (проверим есть ли created_at в subscriptions)
    try:
        day_pay = cursor.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE created_at > ?", (day_ago,)
        ).fetchone()[0]

        week_pay = cursor.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE created_at > ?", (week_ago,)
        ).fetchone()[0]

        month_pay = cursor.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE created_at > ?", (month_ago,)
        ).fetchone()[0]

        show_payments = True
    except:
        show_payments = False

    conn.close()

    print("=" * 50)
    print("📊 СТАТИСТИКА БОТА")
    print("=" * 50)
    print(f"👥 Всего пользователей: {total_users}")
    print(f"✅ Активных подписок: {active_subs}")
    print(f"❌ Отменённых подписок: {cancelled_subs}")
    print()
    print("📈 НОВЫЕ ПОЛЬЗОВАТЕЛИ:")
    print(f"  • За день:   {day_users}")
    print(f"  • За неделю: {week_users}")
    print(f"  • За месяц:  {month_users}")

    if show_payments:
        print()
        print("💰 НОВЫЕ ПОДПИСКИ:")
        print(f"  • За день:   {day_pay}")
        print(f"  • За неделю: {week_pay}")
        print(f"  • За месяц:  {month_pay}")

    print("=" * 50)


if __name__ == "__main__":
    get_stats()
