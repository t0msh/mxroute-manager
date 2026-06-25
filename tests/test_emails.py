"""HTTP tests for mailbox CRUD and recovery-email routes."""

from unittest.mock import patch

import pytest

from tests.helpers import (
    auth_post_headers,
    insert_user_with_grants,
    mx_json_response,
    prime_authenticated_session,
)

DOMAIN = "example.com"


@pytest.fixture(autouse=True)
def clear_email_test_tables(db_connection):
    db_connection.execute("DELETE FROM delegations")
    db_connection.execute("DELETE FROM users")
    db_connection.execute("DELETE FROM mailbox_recovery")
    db_connection.commit()


@pytest.fixture
def emails_token(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "editor@local",
        grants=[{"domain": DOMAIN, "permissions": ["emails"]}],
    )
    return prime_authenticated_session(client, "editor@local")


def test_create_email_requires_login(client):
    response = client.post(
        f"/api/domains/{DOMAIN}/email-accounts",
        json={"username": "alex", "password": "Abcd123!"},
    )
    assert response.status_code == 401


def test_create_email_requires_csrf(fresh_db, client, db_connection, emails_token):
    with patch("services.mailbox_provision.audited_mx") as mock_mx:
        response = client.post(
            f"/api/domains/{DOMAIN}/email-accounts",
            json={"username": "alex", "password": "Abcd123!"},
        )

    assert response.status_code == 400
    assert "csrf" in response.get_json()["error"]["message"].lower()
    mock_mx.assert_not_called()


def test_create_email_rejects_invalid_username(fresh_db, client, emails_token):
    with patch("services.mailbox_provision.audited_mx") as mock_mx:
        response = client.post(
            f"/api/domains/{DOMAIN}/email-accounts",
            headers=auth_post_headers(emails_token),
            json={"username": "bad name", "password": "Abcd123!"},
        )

    assert response.status_code == 400
    assert "username" in response.get_json()["error"]["message"].lower()
    mock_mx.assert_not_called()


def test_create_email_rejects_recovery_same_as_mailbox(fresh_db, client, emails_token):
    with patch("services.mailbox_provision.audited_mx") as mock_mx:
        response = client.post(
            f"/api/domains/{DOMAIN}/email-accounts",
            headers=auth_post_headers(emails_token),
            json={
                "username": "alex",
                "password": "Abcd123!",
                "recovery_email": "alex@example.com",
            },
        )

    assert response.status_code == 400
    assert "differ" in response.get_json()["error"]["message"].lower()
    mock_mx.assert_not_called()


def test_create_email_strips_recovery_from_mx_payload(fresh_db, client, emails_token):
    with (
        patch(
            "services.mailbox_provision.audited_mx",
            return_value=mx_json_response({"success": True}, 201),
        ) as mock_mx,
        patch("routes.emails.audit"),
    ):
        response = client.post(
            f"/api/domains/{DOMAIN}/email-accounts",
            headers=auth_post_headers(emails_token),
            json={
                "username": "alex",
                "password": "Abcd123!",
                "recovery_email": "backup@gmail.com",
            },
        )

    assert response.status_code == 201
    mx_payload = mock_mx.call_args[0][2]
    assert "recovery_email" not in mx_payload
    assert mx_payload["username"] == "alex"


def test_create_email_saves_recovery_on_success(
    fresh_db, client, db_connection, emails_token
):
    with (
        patch(
            "services.mailbox_provision.audited_mx",
            return_value=mx_json_response({"success": True}, 201),
        ),
        patch("routes.emails.audit"),
    ):
        response = client.post(
            f"/api/domains/{DOMAIN}/email-accounts",
            headers=auth_post_headers(emails_token),
            json={
                "username": "alex",
                "password": "Abcd123!",
                "recovery_email": "backup@gmail.com",
            },
        )

    assert response.status_code == 201
    assert (
        db_connection.execute(
            "SELECT recovery_email FROM mailbox_recovery WHERE mailbox_email = ?",
            ("alex@example.com",),
        ).fetchone()[0]
        == "backup@gmail.com"
    )


def test_list_emails_merges_recovery_from_db(
    fresh_db, client, db_connection, emails_token
):
    db_connection.execute(
        "INSERT INTO mailbox_recovery (mailbox_email, recovery_email, updated_at) VALUES (?, ?, ?)",
        ("alex@example.com", "backup@gmail.com", "2026-01-01T00:00:00+00:00"),
    )
    db_connection.commit()

    with patch(
        "routes.emails.mx_domain_request_raw",
        return_value=({"success": True, "data": [{"username": "alex"}]}, 200),
    ):
        response = client.get(f"/api/domains/{DOMAIN}/email-accounts")

    assert response.status_code == 200
    account = response.get_json()["data"][0]
    assert account["recovery_email"] == "backup@gmail.com"
    assert account["has_recovery_email"] is True


def test_update_recovery_email_sets_value(fresh_db, client, emails_token):
    with patch("routes.emails.audit"):
        response = client.patch(
            f"/api/domains/{DOMAIN}/email-accounts/alex/recovery",
            headers=auth_post_headers(emails_token),
            json={"recovery_email": "backup@gmail.com"},
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["recovery_email"] == "backup@gmail.com"


def test_update_recovery_email_clears_value(
    fresh_db, client, db_connection, emails_token
):
    db_connection.execute(
        "INSERT INTO mailbox_recovery (mailbox_email, recovery_email, updated_at) VALUES (?, ?, ?)",
        ("alex@example.com", "backup@gmail.com", "2026-01-01T00:00:00+00:00"),
    )
    db_connection.commit()

    with patch("routes.emails.audit"):
        response = client.patch(
            f"/api/domains/{DOMAIN}/email-accounts/alex/recovery",
            headers=auth_post_headers(emails_token),
            json={"recovery_email": ""},
        )

    assert response.status_code == 200
    assert (
        db_connection.execute(
            "SELECT COUNT(*) FROM mailbox_recovery WHERE mailbox_email = ?",
            ("alex@example.com",),
        ).fetchone()[0]
        == 0
    )


def test_update_recovery_email_rejects_invalid(fresh_db, client, emails_token):
    with patch("routes.emails.audit"):
        response = client.patch(
            f"/api/domains/{DOMAIN}/email-accounts/alex/recovery",
            headers=auth_post_headers(emails_token),
            json={"recovery_email": "alex@example.com"},
        )

    assert response.status_code == 400


def test_delete_email_removes_recovery_on_success(
    fresh_db, client, db_connection, emails_token
):
    db_connection.execute(
        "INSERT INTO mailbox_recovery (mailbox_email, recovery_email, updated_at) VALUES (?, ?, ?)",
        ("alex@example.com", "backup@gmail.com", "2026-01-01T00:00:00+00:00"),
    )
    db_connection.commit()

    with patch(
        "routes.emails.audited_mx_domain",
        return_value=mx_json_response({"success": True}, 200),
    ):
        response = client.delete(
            f"/api/domains/{DOMAIN}/email-accounts/alex",
            headers=auth_post_headers(emails_token),
        )

    assert response.status_code == 200
    assert (
        db_connection.execute(
            "SELECT COUNT(*) FROM mailbox_recovery WHERE mailbox_email = ?",
            ("alex@example.com",),
        ).fetchone()[0]
        == 0
    )


def test_update_email_rejects_invalid_username(fresh_db, client, emails_token):
    with patch("routes.emails.audited_mx_domain") as mock_mx:
        response = client.patch(
            f"/api/domains/{DOMAIN}/email-accounts/bad name",
            headers=auth_post_headers(emails_token),
            json={"password": "Abcd123!"},
        )

    assert response.status_code == 400
    mock_mx.assert_not_called()


def test_update_email_password_calls_mxroute(fresh_db, client, emails_token):
    with patch(
        "routes.emails.audited_mx_domain",
        return_value=mx_json_response({"success": True}, 200),
    ) as mock_mx:
        response = client.patch(
            f"/api/domains/{DOMAIN}/email-accounts/alex",
            headers=auth_post_headers(emails_token),
            json={"password": "Newpass1!"},
        )

    assert response.status_code == 200
    mock_mx.assert_called_once()
    assert mock_mx.call_args[0][0] == "PATCH"
    assert mock_mx.call_args[0][4] == "mailbox.password_update"


def test_delete_email_rejects_invalid_username(fresh_db, client, emails_token):
    with patch("routes.emails.audited_mx_domain") as mock_mx:
        response = client.delete(
            f"/api/domains/{DOMAIN}/email-accounts/bad name",
            headers=auth_post_headers(emails_token),
        )

    assert response.status_code == 400
    mock_mx.assert_not_called()


def test_mail_client_settings_requires_login(client):
    response = client.get(f"/api/domains/{DOMAIN}/mail-client-settings")
    assert response.status_code == 401


def test_mail_client_settings_forbidden_without_emails_grant(
    fresh_db, client, db_connection
):
    insert_user_with_grants(
        db_connection,
        "viewer@local",
        grants=[{"domain": DOMAIN, "permissions": ["forwarders"]}],
    )
    prime_authenticated_session(client, "viewer@local")
    response = client.get(f"/api/domains/{DOMAIN}/mail-client-settings")
    assert response.status_code == 403


def test_mail_client_settings_returns_domain_settings(fresh_db, client, emails_token):
    settings = {
        "domain": DOMAIN,
        "mail_host": f"mail.{DOMAIN}",
        "imap": {"host": f"mail.{DOMAIN}", "port": 993, "encryption": "ssl"},
        "smtp_ssl": {"host": f"mail.{DOMAIN}", "port": 465, "encryption": "ssl"},
        "smtp_starttls": {
            "host": f"mail.{DOMAIN}",
            "port": 587,
            "encryption": "starttls",
        },
        "webmail": {"url": None, "status": "skipped"},
        "username_note": "Use your full email address as the username.",
    }
    with patch(
        "routes.emails.build_domain_mail_client_settings",
        return_value=settings,
    ):
        response = client.get(f"/api/domains/{DOMAIN}/mail-client-settings")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["mail_host"] == f"mail.{DOMAIN}"
