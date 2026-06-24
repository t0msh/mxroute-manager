"""Tests for bulk mailbox CSV import validation."""

import pytest

from services.mailbox_import import normalize_import_row, preview_mailbox_import
from tests.helpers import insert_user_with_grants

DOMAIN = "example.com"
OTHER = "other.example.com"


@pytest.fixture(autouse=True)
def clear_users(db_connection):
    db_connection.execute("DELETE FROM delegations")
    db_connection.execute("DELETE FROM users")
    db_connection.commit()


def test_normalize_import_row_from_email_column():
    row = normalize_import_row(
        {"email": "Alex@Example.com", "password": "Abcd123!"},
        default_domain=DOMAIN,
    )
    assert row["username"] == "alex"
    assert row["domain"] == DOMAIN


def test_normalize_import_row_uses_domain_column():
    row = normalize_import_row(
        {
            "domain": OTHER,
            "username": "sales",
            "password": "Abcd123!",
        },
        default_domain=DOMAIN,
    )
    assert row["domain"] == OTHER
    assert row["username"] == "sales"


def test_preview_rejects_invalid_username(fresh_db, db_connection):
    insert_user_with_grants(
        db_connection,
        "editor@local",
        grants=[{"domain": DOMAIN, "permissions": ["emails"]}],
    )
    user = {"email": "editor@local", "is_admin": False, "domain_grants": {DOMAIN: ["emails"]}}
    preview = preview_mailbox_import(
        [{"username": "bad name", "password": "Abcd123!"}],
        user=user,
        default_domain=DOMAIN,
    )
    assert preview["ok"] is True
    assert preview["data"]["summary"]["valid"] == 0
    assert preview["data"]["rows"][0]["errors"]


def test_preview_requires_emails_permission(fresh_db, db_connection):
    insert_user_with_grants(
        db_connection,
        "dns@local",
        grants=[{"domain": DOMAIN, "permissions": ["dns"]}],
    )
    user = {"email": "dns@local", "is_admin": False, "domain_grants": {DOMAIN: ["dns"]}}
    preview = preview_mailbox_import(
        [{"username": "alex", "password": "Abcd123!"}],
        user=user,
        default_domain=DOMAIN,
    )
    assert preview["data"]["summary"]["valid"] == 0
    assert "permission" in preview["data"]["rows"][0]["errors"][0].lower()


def test_preview_route(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "editor@local",
        grants=[{"domain": DOMAIN, "permissions": ["emails"]}],
    )
    from tests.helpers import auth_post_headers, prime_authenticated_session

    token = prime_authenticated_session(client, "editor@local")
    response = client.post(
        "/api/email-accounts/import/preview",
        headers=auth_post_headers(token),
        json={
            "default_domain": DOMAIN,
            "existing_by_domain": {DOMAIN: []},
            "rows": [
                {"username": "alice", "password": "Abcd123!", "quota": 1024, "limit": 9600},
                {"username": "bob", "password": "short"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["summary"]["total"] == 2
    assert data["summary"]["valid"] == 1
    assert data["rows"][1]["errors"]


def test_preview_flags_existing_mailbox(fresh_db, db_connection):
    insert_user_with_grants(
        db_connection,
        "editor@local",
        grants=[{"domain": DOMAIN, "permissions": ["emails"]}],
    )
    user = {"email": "editor@local", "is_admin": False, "domain_grants": {DOMAIN: ["emails"]}}
    preview = preview_mailbox_import(
        [
            {"username": "alice", "password": "Abcd123!"},
            {"username": "bob", "password": "Abcd123!"},
        ],
        user=user,
        default_domain=DOMAIN,
        existing_by_domain={DOMAIN: ["alice"]},
    )

    assert preview["data"]["summary"]["valid"] == 1
    assert preview["data"]["summary"]["already_exists"] == 1
    assert preview["data"]["rows"][0]["already_exists"] is True
    assert preview["data"]["rows"][1]["valid"] is True
