from admin import UsersPaginator, _parse_usernames
from messages import format_message


def test_users_paginator_page_and_keyboard():
    users = [
        {"user_id": 1, "username": "user1", "first_name": "User One"},
        {"user_id": 2, "username": "", "first_name": "User Two"},
        {"user_id": 3, "username": "user3", "first_name": "User Three"},
    ]
    paginator = UsersPaginator(users, page=0, per_page=2)
    page_users = paginator.get_page_users()

    assert [u["user_id"] for u in page_users] == [1, 2]
    keyboard = paginator.get_keyboard()
    assert keyboard.inline_keyboard[0][0].callback_data == "user_profile_1"
    assert keyboard.inline_keyboard[1][0].callback_data == "user_profile_2"


def test_format_message_with_known_and_unknown_key():
    rendered = format_message("status_active", days_left=7)
    assert "Дней осталось: 7" in rendered
    assert format_message("missing_key") == ""


def test_parse_usernames_normalizes_and_deduplicates():
    raw = "@Alice, bob\nCHARLIE ; @alice"
    assert _parse_usernames(raw) == ["alice", "bob", "charlie"]
