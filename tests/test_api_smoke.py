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


def test_cors_smart_validation():
    # 1. Null Origin (file:// protocol local launches)
    url = f"{BASE_URL}/api/health"
    with httpx.Client() as client:
        resp = client.get(url, headers={"Origin": "null"})
        assert resp.status_code == 200
        assert resp.headers.get("Access-Control-Allow-Origin") == "null"

    # 2. Localhost dynamic Origin
    with httpx.Client() as client:
        resp = client.get(url, headers={"Origin": "http://localhost:12345"})
        assert resp.status_code == 200
        assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:12345"

    # 3. 127.0.0.1 dynamic Origin
    with httpx.Client() as client:
        resp = client.get(url, headers={"Origin": "http://127.0.0.1:9999"})
        assert resp.status_code == 200
        assert resp.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:9999"

    # 4. Unauthorized domain -> falls back to first allowed origin
    with httpx.Client() as client:
        resp = client.get(url, headers={"Origin": "https://unauthorized-domain.com"})
        assert resp.status_code == 200
        assert resp.headers.get("Access-Control-Allow-Origin") == "https://olegfire07.github.io"


def test_generate_validation():
    url = f"{BASE_URL}/api/generate"
    # 1. Missing required fields
    with httpx.Client() as client:
        resp = client.post(url, json={"department_number": "123"})
        assert resp.status_code == 400
        assert "Missing field" in resp.json()["error"]

    # 2. Future date rejection
    future_payload = {
        "department_number": "123",
        "issue_number": "456",
        "ticket_number": "789",
        "date": "25.12.2030", # Future date
        "region": "Москва",
        "items": []
    }
    with httpx.Client() as client:
        resp = client.post(url, json=future_payload)
        assert resp.status_code == 400
        assert "будущую дату" in resp.json()["error"]

    # 3. Invalid date format
    invalid_date_payload = {
        "department_number": "123",
        "issue_number": "456",
        "ticket_number": "789",
        "date": "2030-12-25", # Wrong format
        "region": "Москва",
        "items": []
    }
    with httpx.Client() as client:
        resp = client.post(url, json=invalid_date_payload)
        assert resp.status_code == 400
        assert "формат даты" in resp.json()["error"]


def test_api_authorization():
    import modern_bot.api
    url = f"{BASE_URL}/api/stats"
    
    # Enable auth token for test
    original_token = modern_bot.api.API_AUTH_TOKEN
    modern_bot.api.API_AUTH_TOKEN = "TEST_SECRET_TOKEN"
    
    try:
        # 1. Request without token -> expect 401
        with httpx.Client() as client:
            resp = client.get(url)
            assert resp.status_code == 401
            assert resp.json()["error"] == "Unauthorized"

        # 2. Request with invalid token -> expect 401
        with httpx.Client() as client:
            resp = client.get(url, headers={"X-API-KEY": "WRONG_TOKEN"})
            assert resp.status_code == 401

        # 3. Request with valid token -> expect 200 (or other status if month dir is empty, but not 401)
        with httpx.Client() as client:
            resp = client.get(url, headers={"X-API-KEY": "TEST_SECRET_TOKEN"})
            assert resp.status_code in (200, 500) # Directory empty might return 200 or 500
            assert resp.status_code != 401
            
    finally:
        # Restore token
        modern_bot.api.API_AUTH_TOKEN = original_token


def test_quiz_submission():
    import sqlite3
    from modern_bot.config import DATABASE_FILE
    
    url = f"{BASE_URL}/api/quiz/submit"
    
    # 1. Invalid JSON
    with httpx.Client() as client:
        resp = client.post(url, content="invalid-json")
        assert resp.status_code == 400
        assert "JSON" in resp.json()["error"]

    # 2. Invalid user_id
    with httpx.Client() as client:
        resp = client.post(url, json={"user_id": "abc"})
        assert resp.status_code == 400
        assert "user_id" in resp.json()["error"]

    # 3. Invalid statistics (non-integer correct)
    with httpx.Client() as client:
        resp = client.post(url, json={"user_id": 9999, "correct": "abc"})
        assert resp.status_code == 400
        assert "stats" in resp.json()["error"]

    # 4. Valid quiz submission
    test_user_id = 999999
    test_region = "ТестРегион"
    payload = {
        "user_id": test_user_id,
        "region": test_region,
        "correct": 7,
        "wrong": 3,
        "total": 10
    }
    
    with httpx.Client() as client:
        resp = client.post(url, json=payload)
        assert resp.status_code == 200
        
    # Verify in SQLite database
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT correct, wrong, total FROM quiz_attempts WHERE user_id = ? AND region = ?", (test_user_id, test_region))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 7
        assert row[1] == 3
        assert row[2] == 10
    finally:
        # Clean up database
        cursor.execute("DELETE FROM quiz_attempts WHERE user_id = ?", (test_user_id,))
        conn.commit()
        conn.close()



