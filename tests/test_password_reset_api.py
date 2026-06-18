"""HTTP tests for the public mailbox password-reset API."""
from unittest.mock import patch

import pytest

from tests.helpers import auth_post_headers, csrf_token_from_response


MAILBOX = "user@example.com"
RECOVERY = "backup@gmail.com"


@pytest.fixture(autouse=True)
def clear_password_reset_state(fresh_db, db_connection):
    db_connection.execute("DELETE FROM mailbox_recovery")
    db_connection.execute("DELETE FROM password_reset_tokens")
    db_connection.commit()
    from routes import password_reset as pr_module
    with pr_module._RATE_LOCK:
        pr_module._RATE_BUCKETS.clear()


def _public_csrf(client):
    csrf_token_from_response(client, path="/api/public/password-reset/status", host="localhost")
    with client.session_transaction() as sess:
        return sess.get("csrf_token")


def test_password_reset_status_is_public(client):
    response = client.get("/api/public/password-reset/status")
    assert response.status_code == 200
    assert "enabled" in response.get_json()["data"]


@pytest.mark.parametrize("mailbox", [
    "not-an-email",
    "missing@example.com",
    "user@other.com",
])
def test_reset_request_never_leaks_enumeration(client, mailbox):
    with patch("routes.password_reset.is_password_reset_available", return_value=True), \
         patch("routes.password_reset.send_password_reset_email") as mock_send:
        csrf = _public_csrf(client)
        response = client.post(
            "/api/public/password-reset/request",
            headers=auth_post_headers(csrf),
            json={"mailbox_email": mailbox},
        )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    mock_send.assert_not_called()


def test_reset_request_sends_email_when_recovery_exists(fresh_db, client, db_connection):
    db_connection.execute(
        "INSERT INTO mailbox_recovery (mailbox_email, recovery_email, updated_at) VALUES (?, ?, ?)",
        (MAILBOX, RECOVERY, "2026-01-01T00:00:00+00:00"),
    )
    db_connection.commit()

    with patch("routes.password_reset.is_password_reset_available", return_value=True), \
         patch("routes.password_reset.send_password_reset_email") as mock_send, \
         patch("routes.password_reset.write_audit_log"):
        csrf = _public_csrf(client)
        response = client.post(
            "/api/public/password-reset/request",
            headers=auth_post_headers(csrf),
            json={"mailbox_email": MAILBOX},
        )

    assert response.status_code == 200
    mock_send.assert_called_once()
    assert mock_send.call_args[0][0] == RECOVERY


def test_reset_confirm_rejects_weak_password(fresh_db, client):
    token = fresh_db.create_reset_token(MAILBOX)
    with patch("routes.password_reset.is_password_reset_available", return_value=True), \
         patch("routes.password_reset.mx_request_raw") as mock_mx:
        csrf = _public_csrf(client)
        response = client.post(
            "/api/public/password-reset/confirm",
            headers=auth_post_headers(csrf),
            json={"token": token, "password": "weak"},
        )

    assert response.status_code == 400
    mock_mx.assert_not_called()


def test_reset_confirm_updates_mailbox_password(fresh_db, client):
    token = fresh_db.create_reset_token(MAILBOX)

    with patch("routes.password_reset.is_password_reset_available", return_value=True), \
         patch("routes.password_reset.mx_request_raw", return_value=({"success": True}, 200)), \
         patch("routes.password_reset.write_audit_log"):
        csrf = _public_csrf(client)
        response = client.post(
            "/api/public/password-reset/confirm",
            headers=auth_post_headers(csrf),
            json={"token": token, "password": "Abcd123!"},
        )

    assert response.status_code == 200
    assert fresh_db.consume_reset_token(token) is None


def test_reset_confirm_rejects_reused_token(fresh_db, client):
    token = fresh_db.create_reset_token(MAILBOX)
    fresh_db.consume_reset_token(token)

    with patch("routes.password_reset.is_password_reset_available", return_value=True), \
         patch("routes.password_reset.mx_request_raw") as mock_mx:
        csrf = _public_csrf(client)
        response = client.post(
            "/api/public/password-reset/confirm",
            headers=auth_post_headers(csrf),
            json={"token": token, "password": "Abcd123!"},
        )

    assert response.status_code == 400
    mock_mx.assert_not_called()


def test_reset_confirm_unavailable_returns_503(client):
    with patch("routes.password_reset.is_password_reset_available", return_value=False):
        csrf = _public_csrf(client)
        response = client.post(
            "/api/public/password-reset/confirm",
            headers=auth_post_headers(csrf),
            json={"token": "any", "password": "Abcd123!"},
        )

    assert response.status_code == 503
