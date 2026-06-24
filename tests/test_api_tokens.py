"""Tests for API token authentication and admin routes."""

from unittest.mock import patch

import pytest

from models.db_api_tokens import create_api_token, lookup_api_token
from tests.helpers import (
    auth_post_headers,
    insert_user_with_grants,
    mx_json_response,
    prime_authenticated_session,
)

DOMAIN = "example.com"


@pytest.fixture(autouse=True)
def clear_users(db_connection):
    db_connection.execute("DELETE FROM api_tokens")
    db_connection.execute("DELETE FROM delegations")
    db_connection.execute("DELETE FROM users")
    db_connection.commit()


@pytest.fixture
def admin_token(fresh_db, client, db_connection):
    insert_user_with_grants(db_connection, "admin@local", is_admin=True)
    return prime_authenticated_session(client, "admin@local")


@pytest.fixture
def emails_token(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "editor@local",
        grants=[{"domain": DOMAIN, "permissions": ["emails"]}],
    )
    return prime_authenticated_session(client, "editor@local")


def test_create_and_lookup_api_token(fresh_db):
    record, raw = create_api_token(
        label="ci",
        is_admin=False,
        grants=[{"domain": DOMAIN, "permissions": ["emails", "dns"]}],
    )
    assert raw.startswith("mxm_")
    assert record["label"] == "ci"
    loaded = lookup_api_token(raw)
    assert loaded["id"] == record["id"]
    assert loaded["token_prefix"] == record["token_prefix"]


def test_api_token_auth_allows_scoped_route(fresh_db, client):
    _record, raw = create_api_token(
        label="mailbox-bot",
        grants=[{"domain": DOMAIN, "permissions": ["emails"]}],
    )
    with patch(
        "routes.emails.mx_request",
        return_value=mx_json_response({"success": True, "data": []}),
    ):
        response = client.get(
            f"/api/domains/{DOMAIN}/email-accounts",
            headers={"Authorization": f"Bearer {raw}"},
        )
    assert response.status_code == 200


def test_api_token_auth_denies_wrong_permission(fresh_db, client):
    _record, raw = create_api_token(
        label="dns-only",
        grants=[{"domain": DOMAIN, "permissions": ["dns"]}],
    )
    response = client.get(
        f"/api/domains/{DOMAIN}/email-accounts",
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert response.status_code == 403


def test_api_token_skips_csrf(fresh_db, client):
    _record, raw = create_api_token(
        label="writer",
        grants=[{"domain": DOMAIN, "permissions": ["emails"]}],
    )
    with patch(
        "routes.emails.audited_mx",
        return_value=mx_json_response({"success": True}, 201),
    ):
        response = client.post(
            f"/api/domains/{DOMAIN}/email-accounts",
            headers={"Authorization": f"Bearer {raw}"},
            json={"username": "alex", "password": "Abcd123!"},
        )
    assert response.status_code == 201


def test_admin_can_create_api_token(fresh_db, client, admin_token):
    response = client.post(
        "/api/admin/api-tokens",
        headers=auth_post_headers(admin_token),
        json={
            "label": "deploy",
            "is_admin": True,
        },
    )
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["token"].startswith("mxm_")
    assert data["label"] == "deploy"


def test_non_admin_cannot_manage_api_tokens(fresh_db, client, emails_token):
    response = client.get(
        "/api/admin/api-tokens",
        headers=auth_post_headers(emails_token),
    )
    assert response.status_code == 403


def test_revoke_api_token(fresh_db, client, admin_token):
    record, raw = create_api_token(
        label="temp",
        grants=[{"domain": DOMAIN, "permissions": ["emails"]}],
    )
    revoke = client.delete(
        f"/api/admin/api-tokens/{record['id']}",
        headers=auth_post_headers(admin_token),
    )
    assert revoke.status_code == 200
    assert lookup_api_token(raw) is None
