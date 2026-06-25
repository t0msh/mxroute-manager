"""HTTP tests for login, session, and delegated access control."""

from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from models.db import ALL_PERMISSIONS
from routes.auth import build_session_user
from tests.helpers import (
    auth_post_headers,
    insert_user_with_grants,
    mx_json_response,
    prime_authenticated_session,
)


@pytest.fixture(autouse=True)
def clear_auth_tables(db_connection):
    """Each test gets a clean users/delegations slate."""
    db_connection.execute("DELETE FROM delegations")
    db_connection.execute("DELETE FROM users")
    db_connection.commit()


def test_api_requires_login(client):
    response = client.get("/api/domains")
    assert response.status_code == 401
    assert response.get_json()["error"]["message"] == "Unauthorized"


def test_local_user_login_success(fresh_db, client, db_connection):
    db_connection.execute(
        "INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, ?)",
        ("billy", generate_password_hash("Abcd123!"), 0),
    )
    db_connection.commit()

    response = client.post(
        "/login",
        data={"username": "billy", "password": "Abcd123!"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with client.session_transaction() as sess:
        user = sess.get("user")
        assert user and user.get("email") == "billy"


def test_me_returns_null_user_when_logged_out(client):
    response = client.get("/api/me")
    assert response.status_code == 401


def test_me_returns_delegate_profile(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "editor@local",
        grants=[{"domain": "example.com", "permissions": ["dashboard", "emails"]}],
    )
    prime_authenticated_session(client, "editor@local")

    response = client.get("/api/me")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["user"]["email"] == "editor@local"
    assert payload["user"]["is_admin"] is False
    assert payload["user"]["delegated_domains"] == ["example.com"]
    assert payload["user"]["domain_grants"]["example.com"] == ["dashboard", "emails"]


def test_delegate_can_list_emails_with_permission(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "editor@local",
        grants=[{"domain": "example.com", "permissions": ["emails"]}],
    )
    prime_authenticated_session(client, "editor@local")

    mx_payload = {"success": True, "data": [{"username": "alex"}]}

    with patch(
        "routes.emails.mx_domain_request_raw",
        return_value=(mx_payload, 200),
    ):
        response = client.get("/api/domains/example.com/email-accounts")

    assert response.status_code == 200
    assert response.get_json()["data"][0]["username"] == "alex"


def test_delegate_forbidden_without_emails_permission(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "viewer@local",
        grants=[{"domain": "example.com", "permissions": ["dashboard"]}],
    )
    token = prime_authenticated_session(client, "viewer@local")

    with patch("routes.emails.audited_mx_domain") as mock_mx:
        response = client.post(
            "/api/domains/example.com/email-accounts",
            headers=auth_post_headers(token),
            json={"username": "alex", "password": "Abcd123!"},
        )

    assert response.status_code == 403
    assert "emails" in response.get_json()["error"]["message"]
    mock_mx.assert_not_called()


def test_delegate_forbidden_on_unassigned_domain(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "editor@local",
        grants=[{"domain": "example.com", "permissions": ["emails"]}],
    )
    prime_authenticated_session(client, "editor@local")

    response = client.get("/api/domains/other.com/email-accounts")
    assert response.status_code == 403
    assert (
        response.get_json()["error"]["message"]
        == "Forbidden: You do not have access to domain 'other.com'"
    )


def test_domain_list_filtered_for_delegate(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "editor@local",
        grants=[{"domain": "allowed.com", "permissions": ["dashboard"]}],
    )
    prime_authenticated_session(client, "editor@local")

    mx_res = {"success": True, "data": ["allowed.com", "secret.com"]}
    with patch("routes.domains.mx_request_raw", return_value=(mx_res, 200)):
        response = client.get("/api/domains")

    assert response.status_code == 200
    assert response.get_json()["data"] == ["allowed.com"]


def test_create_domain_requires_admin(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "editor@local",
        grants=[{"domain": "example.com", "permissions": list(ALL_PERMISSIONS)}],
    )
    token = prime_authenticated_session(client, "editor@local")

    with patch("routes.domains.audited_mx_domain") as mock_mx:
        response = client.post(
            "/api/domains",
            headers=auth_post_headers(token),
            json={"domain": "new.com"},
        )

    assert response.status_code == 403
    mock_mx.assert_not_called()


def test_admin_can_list_delegations(fresh_db, client, db_connection):
    insert_user_with_grants(db_connection, "admin@local", is_admin=True)
    insert_user_with_grants(
        db_connection,
        "editor@local",
        grants=[{"domain": "example.com", "permissions": ["emails"]}],
    )
    prime_authenticated_session(client, "admin@local")

    response = client.get("/api/admin/delegations")
    assert response.status_code == 200
    emails = {row["email"] for row in response.get_json()["data"]}
    assert "editor@local" in emails


def test_non_admin_forbidden_from_delegations_api(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "editor@local",
        grants=[{"domain": "example.com", "permissions": ["emails"]}],
    )
    prime_authenticated_session(client, "editor@local")

    response = client.get("/api/admin/delegations")
    assert response.status_code == 403
    assert "Admin" in response.get_json()["error"]["message"]


def test_admin_can_create_delegation(fresh_db, client, db_connection):
    insert_user_with_grants(db_connection, "admin@local", is_admin=True)
    token = prime_authenticated_session(client, "admin@local")

    with patch("routes.admin_delegations.audit"):
        response = client.post(
            "/api/admin/delegations",
            headers=auth_post_headers(token),
            json={
                "email": "newuser@local",
                "password": "Abcd123!",
                "grants": [
                    {"domain": "example.com", "permissions": ["emails", "dashboard"]}
                ],
            },
        )

    assert response.status_code == 200
    assert response.get_json()["success"] is True

    user = build_session_user("newuser@local")
    assert user["domain_grants"]["example.com"] == ["emails", "dashboard"]


def test_admin_cannot_delete_own_delegation(fresh_db, client, db_connection):
    insert_user_with_grants(db_connection, "admin@local", is_admin=True)
    token = prime_authenticated_session(client, "admin@local")

    response = client.delete(
        "/api/admin/delegations/admin@local",
        headers=auth_post_headers(token),
    )
    assert response.status_code == 409
    assert "cannot revoke" in response.get_json()["error"]["message"].lower()


def test_delegation_create_requires_domain_grants(fresh_db, client, db_connection):
    insert_user_with_grants(db_connection, "admin@local", is_admin=True)
    token = prime_authenticated_session(client, "admin@local")

    response = client.post(
        "/api/admin/delegations",
        headers=auth_post_headers(token),
        json={
            "email": "empty@local",
            "password": "Abcd123!",
            "grants": [],
        },
    )
    assert response.status_code == 400
    assert "domain" in response.get_json()["error"]["message"].lower()
