import os

import httpx
import pytest

BASE_URL = os.getenv("API_BASE", "http://127.0.0.1:8080").rstrip("/")


def _get(path: str) -> httpx.Response:
    url = f"{BASE_URL}{path}"
    try:
        with httpx.Client(timeout=5.0) as client:
            return client.get(url)
    except httpx.RequestError as exc:
        pytest.skip(f"API not reachable: {exc}")


def test_health():
    resp = _get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "bot" in data
    assert "database" in data


def test_super_admin_health():
    resp = _get("/api/super-admin/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "uptime" in data


def test_super_admin_stats():
    resp = _get("/api/super-admin/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_users" in data
    assert "total_tickets" in data


def test_super_admin_page():
    resp = _get("/super-admin")
    assert resp.status_code == 200
    content_type = resp.headers.get("content-type", "")
    assert "text/html" in content_type


def test_super_admin_logs():
    resp = _get("/api/super-admin/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data


def test_super_admin_users_endpoint():
    resp = _get("/api/super-admin/users")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_super_admin_quiz_stats():
    resp = _get("/api/super-admin/quiz-stats?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_attempts" in data
    assert "regions" in data


def test_check_ticket_endpoint():
    import sqlite3
    from modern_bot.config import DATABASE_FILE

    # 1. Missing ticket param
    resp = _get("/api/check-ticket")
    assert resp.status_code == 400
    
    # 2. Non-existent ticket
    resp = _get("/api/check-ticket?ticket=99999999999")
    assert resp.status_code == 200
    data = resp.json()
    assert data["duplicate"] is False

    # 3. Existing ticket (seeded dynamically)
    test_ticket = "88888888888"
    test_user_id = 999999999
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        # Seed user
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, last_active) VALUES (?, ?, ?, ?, ?)",
            (test_user_id, "test_helper", "Иван", "Тестовый", "2026-05-19")
        )
        # Seed processed ticket
        cursor.execute(
            "INSERT OR REPLACE INTO processed_tickets (ticket_number, issue_number, date, user_id) VALUES (?, ?, ?, ?)",
            (test_ticket, "ISSUE-123", "19.05.2026", test_user_id)
        )
        conn.commit()
        
        # Query API for seeded ticket
        resp = _get(f"/api/check-ticket?ticket={test_ticket}")
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["duplicate"] is True
        assert data["user"] == "Иван Тестовый"
        assert data["date"] == "19.05.2026"
        
    finally:
        # Clean up database
        cursor.execute("DELETE FROM processed_tickets WHERE ticket_number = ?", (test_ticket,))
        cursor.execute("DELETE FROM users WHERE user_id = ?", (test_user_id,))
        conn.commit()
        conn.close()


def test_clean_reply_markup_fallback():
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from modern_bot.handlers.common import clean_reply_markup_fallback

    # Create a markup containing premium fields
    button_premium = InlineKeyboardButton(
        text="Premium Button",
        callback_data="test_callback",
        style="primary",
        icon_custom_emoji_id="12345"
    )
    button_normal = InlineKeyboardButton(
        text="Normal Button",
        callback_data="test_normal"
    )

    markup = InlineKeyboardMarkup([[button_premium, button_normal]])

    # Call the fallback function
    cleaned = clean_reply_markup_fallback(markup)

    # Verify that the returned markup is a new InlineKeyboardMarkup
    assert isinstance(cleaned, InlineKeyboardMarkup)
    assert len(cleaned.inline_keyboard) == 1
    row = cleaned.inline_keyboard[0]
    assert len(row) == 2

    # Check button 1: premium fields should be stripped
    btn1 = row[0]
    assert btn1.text == "Premium Button"
    assert btn1.callback_data == "test_callback"
    btn1_dict = btn1.to_dict()
    assert "style" not in btn1_dict
    assert "icon_custom_emoji_id" not in btn1_dict

    # Check button 2: should remain untouched
    btn2 = row[1]
    assert btn2.text == "Normal Button"
    assert btn2.callback_data == "test_normal"


