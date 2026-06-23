"""Tests for login brute-force protection."""

import pytest
from werkzeug.security import generate_password_hash

from routes import auth as auth_module


@pytest.fixture(autouse=True)
def clean_login_state(fresh_db, db_connection):
    db_connection.execute("DELETE FROM users")
    db_connection.commit()
    auth_module._login_limiter.clear()
    yield
    auth_module._login_limiter.clear()


def _fail_login(client, username="admin", password="wrong-password"):
    return client.post("/login", data={"username": username, "password": password})


def test_login_blocks_after_too_many_failures(client):
    for _ in range(auth_module._LOGIN_USER_LIMIT):
        resp = _fail_login(client)
        assert resp.status_code == 200  # re-rendered login form with an error

    blocked = _fail_login(client)
    assert blocked.status_code == 429
    assert b"Too many login attempts" in blocked.data


def test_successful_login_clears_failure_counter(client, db_connection):
    db_connection.execute(
        "INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, ?)",
        ("billy", generate_password_hash("Abcd123!"), 0),
    )
    db_connection.commit()

    for _ in range(auth_module._LOGIN_USER_LIMIT - 1):
        assert _fail_login(client, username="billy").status_code == 200

    ok = client.post("/login", data={"username": "billy", "password": "Abcd123!"})
    assert ok.status_code == 302

    client.get("/logout")

    # Counter was reset on success, so a fresh failure is not immediately blocked.
    assert _fail_login(client, username="billy").status_code == 200
