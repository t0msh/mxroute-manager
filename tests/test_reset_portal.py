"""Tests for per-domain branded reset portals."""
import io
import os
import sqlite3

import pytest

from services.reset_portal import get_portal_branding_context
from utils.themes import normalize_theme
from utils.validators import validate_subdomain_prefix
from tests.helpers import csrf_token_from_response, insert_user_with_grants, prime_authenticated_session, auth_post_headers


@pytest.fixture(autouse=True)
def clear_reset_portals():
    conn = sqlite3.connect(os.environ["DATABASE_FILE"])
    conn.execute("DELETE FROM domain_reset_portals")
    conn.commit()
    conn.close()


def test_subdomain_prefix_validation():
    ok, _ = validate_subdomain_prefix("reset")
    assert ok is True
    ok, _ = validate_subdomain_prefix("password")
    assert ok is True

    ok, message = validate_subdomain_prefix("")
    assert ok is False

    ok, message = validate_subdomain_prefix("mail")
    assert ok is False
    assert "reserved" in message.lower()

    ok, message = validate_subdomain_prefix("-bad")
    assert ok is False


def test_reset_portal_crud_and_host_lookup(fresh_db):
    ok, message = fresh_db.upsert_reset_portal("example.com", True, "reset", "Example Org")
    assert ok is True
    assert message == ""

    portal = fresh_db.get_reset_portal("example.com")
    assert portal["enabled"] is True
    assert portal["subdomain_prefix"] == "reset"
    assert portal["portal_host"] == "reset.example.com"
    assert portal["portal_title"] == "Example Org"
    assert portal["portal_theme"] == "emerald"

    by_host = fresh_db.get_reset_portal_by_host("reset.example.com")
    assert by_host["domain"] == "example.com"

    fresh_db.upsert_reset_portal("other.com", True, "password", "")
    assert fresh_db.get_reset_portal_by_host("password.other.com")["domain"] == "other.com"
    assert fresh_db.get_reset_portal_by_host("reset.example.com")["domain"] == "example.com"


def test_reset_portal_theme_round_trip_and_validation(fresh_db):
    ok, _ = fresh_db.upsert_reset_portal("example.com", True, "reset", "Example", "indigo-light")
    assert ok is True
    portal = fresh_db.get_reset_portal("example.com")
    assert portal["portal_theme"] == "indigo-light"

    ok, _ = fresh_db.upsert_reset_portal("example.com", True, "reset", "Example", "not-a-theme")
    portal = fresh_db.get_reset_portal("example.com")
    assert portal["portal_theme"] == "emerald"

    branding = get_portal_branding_context(portal)
    assert branding["portal_theme"] == "emerald"
    assert branding["is_reset_portal"] is True


def test_normalize_theme():
    assert normalize_theme("indigo") == "indigo"
    assert normalize_theme(" INDIGO-LIGHT ") == "indigo-light"
    assert normalize_theme("bogus") == "emerald"
    assert normalize_theme(None) == "emerald"


def test_portal_html_includes_theme_attribute(fresh_db, client):
    fresh_db.upsert_reset_portal("example.com", True, "reset", "Example", "crimson")

    response = client.get("/", headers={"Host": "reset.example.com"})
    assert response.status_code == 200
    assert b'data-portal-theme="crimson"' in response.data


def test_build_reset_portal_url(fresh_db):
    fresh_db.upsert_reset_portal("example.com", True, "reset", "")
    prev = os.environ.get("FORCE_HTTPS")
    os.environ["FORCE_HTTPS"] = "true"
    try:
        url = fresh_db.build_reset_portal_url("example.com", "secret-token")
    finally:
        if prev is None:
            os.environ.pop("FORCE_HTTPS", None)
        else:
            os.environ["FORCE_HTTPS"] = prev
    assert url == "https://reset.example.com/reset-password?token=secret-token"

    fresh_db.upsert_reset_portal("example.com", False, "reset", "")
    assert fresh_db.build_reset_portal_url("example.com", "secret-token") is None


def test_portal_host_blocks_admin_paths(fresh_db, client):
    fresh_db.upsert_reset_portal("example.com", True, "reset", "Example")

    response = client.get("/", headers={"Host": "reset.example.com"})
    assert response.status_code == 200
    assert b"Reset Mailbox Password" in response.data

    response = client.get("/login", headers={"Host": "reset.example.com"})
    assert response.status_code == 404


def test_portal_request_rejects_other_domain_mailbox(fresh_db, client):
    fresh_db.upsert_reset_portal("example.com", True, "reset", "")

    csrf_token = csrf_token_from_response(client)
    assert csrf_token

    response = client.post(
        "/api/public/password-reset/request",
        headers={
            "Host": "reset.example.com",
            "X-CSRF-Token": csrf_token,
        },
        json={"mailbox_email": "user@other.com"},
    )
    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_logo_upload_without_prior_save(fresh_db, client, db_connection):
    db_connection.execute(
        "INSERT OR IGNORE INTO users (email, password_hash, is_admin) VALUES (?, ?, 1)",
        ("admin@local", "not-used"),
    )
    db_connection.execute(
        """
        INSERT OR IGNORE INTO delegations (user_id, domain, permissions)
        SELECT id, 'example.com', '["dns"]' FROM users WHERE email = 'admin@local'
        """
    )
    db_connection.commit()

    csrf_token = csrf_token_from_response(client, path="/login", host="localhost")
    assert csrf_token
    with client.session_transaction() as sess:
        sess["user"] = {
            "email": "admin@local",
            "is_admin": True,
            "delegated_domains": ["example.com"],
            "domain_grants": {"example.com": ["dns"]},
        }

    assert fresh_db.get_reset_portal("example.com") is None

    tiny_file = io.BytesIO(b"\x89PNG\r\n\x1a\n")
    response = client.post(
        "/api/domains/example.com/reset-portal/logo",
        headers={"X-CSRF-Token": csrf_token},
        data={"logo": (tiny_file, "logo.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    portal = fresh_db.get_reset_portal("example.com")
    assert portal is not None
    assert portal["enabled"] is False
    assert portal["logo_filename"] == "logo.png"


def test_logo_upload_validation(fresh_db, client, db_connection):
    fresh_db.upsert_reset_portal("example.com", True, "reset", "")

    db_connection.execute(
        "INSERT OR IGNORE INTO users (email, password_hash, is_admin) VALUES (?, ?, 1)",
        ("admin@local", "not-used"),
    )
    db_connection.execute(
        """
        INSERT OR IGNORE INTO delegations (user_id, domain, permissions)
        SELECT id, 'example.com', '["dns"]' FROM users WHERE email = 'admin@local'
        """
    )
    db_connection.commit()

    csrf_token = csrf_token_from_response(client, path="/login", host="localhost")
    assert csrf_token
    with client.session_transaction() as sess:
        sess["user"] = {
            "email": "admin@local",
            "is_admin": True,
            "delegated_domains": ["example.com"],
            "domain_grants": {"example.com": ["dns"]},
        }

    big_file = io.BytesIO(b"x" * (512 * 1024 + 1))
    response = client.post(
        "/api/domains/example.com/reset-portal/logo",
        headers={"X-CSRF-Token": csrf_token},
        data={"logo": (big_file, "logo.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "512" in response.get_json()["error"]["message"]

    tiny_file = io.BytesIO(b"\x89PNG\r\n\x1a\n")
    response = client.post(
        "/api/domains/example.com/reset-portal/logo",
        headers={"X-CSRF-Token": csrf_token},
        data={"logo": (tiny_file, "logo.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    portal = fresh_db.get_reset_portal("example.com")
    assert portal["logo_filename"] == "logo.png"


def test_deploy_reset_portal_uses_current_user_contact_email(fresh_db, client, db_connection):
    from unittest.mock import patch

    fresh_db.upsert_reset_portal("cleaver.click", True, "reset", "Cleaver")
    insert_user_with_grants(
        db_connection,
        "dean@local",
        grants=[{"domain": "cleaver.click", "permissions": ["dns"]}],
    )
    fresh_db.set_user_contact_email("dean@local", "dean.personal@gmail.com")
    token = prime_authenticated_session(client, "dean@local")

    with patch("routes.reset_portal.deploy_reset_portal") as mock_deploy:
        mock_deploy.return_value = {"steps": ["ok"], "host": "reset.cleaver.click"}
        response = client.post(
            "/api/domains/cleaver.click/reset-portal/deploy-dns",
            headers=auth_post_headers(token),
        )

    assert response.status_code == 200
    mock_deploy.assert_called_once_with(
        "cleaver.click",
        "reset",
        admin_email="dean.personal@gmail.com",
    )


def test_deploy_reset_portal_rejects_user_without_contact_email(fresh_db, client, db_connection):
    from unittest.mock import patch

    fresh_db.upsert_reset_portal("cleaver.click", True, "reset", "Cleaver")
    insert_user_with_grants(
        db_connection,
        "dean",
        grants=[{"domain": "cleaver.click", "permissions": ["dns"]}],
    )
    token = prime_authenticated_session(client, "dean")

    with patch("routes.reset_portal.deploy_reset_portal") as mock_deploy:
        response = client.post(
            "/api/domains/cleaver.click/reset-portal/deploy-dns",
            headers=auth_post_headers(token),
        )

    assert response.status_code == 400
    assert "contact email" in response.get_json()["error"]["message"].lower()
    mock_deploy.assert_not_called()
