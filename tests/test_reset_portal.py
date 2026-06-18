"""Tests for per-domain branded reset portals."""
import io
import os
import sqlite3
import sys
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_FILE"] = _tmp.name
os.environ["RESET_PORTAL_CNAME_TARGET"] = "manager.example.com"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db  # noqa: E402
from app import app  # noqa: E402
from utils.validators import validate_subdomain_prefix  # noqa: E402


def setup_function():
    conn = sqlite3.connect(_tmp.name)
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


def test_reset_portal_crud_and_host_lookup():
    db.init_db()
    ok, message = db.upsert_reset_portal("example.com", True, "reset", "Example Org")
    assert ok is True
    assert message == ""

    portal = db.get_reset_portal("example.com")
    assert portal["enabled"] is True
    assert portal["subdomain_prefix"] == "reset"
    assert portal["portal_host"] == "reset.example.com"
    assert portal["portal_title"] == "Example Org"

    by_host = db.get_reset_portal_by_host("reset.example.com")
    assert by_host["domain"] == "example.com"

    db.upsert_reset_portal("other.com", True, "password", "")
    assert db.get_reset_portal_by_host("password.other.com")["domain"] == "other.com"
    assert db.get_reset_portal_by_host("reset.example.com")["domain"] == "example.com"


def test_build_reset_portal_url():
    db.init_db()
    db.upsert_reset_portal("example.com", True, "reset", "")
    prev = os.environ.get("FORCE_HTTPS")
    os.environ["FORCE_HTTPS"] = "true"
    try:
        url = db.build_reset_portal_url("example.com", "secret-token")
    finally:
        if prev is None:
            os.environ.pop("FORCE_HTTPS", None)
        else:
            os.environ["FORCE_HTTPS"] = prev
    assert url == "https://reset.example.com/reset-password?token=secret-token"

    db.upsert_reset_portal("example.com", False, "reset", "")
    assert db.build_reset_portal_url("example.com", "secret-token") is None


def test_portal_host_blocks_admin_paths():
    db.init_db()
    db.upsert_reset_portal("example.com", True, "reset", "Example")
    client = app.test_client()

    response = client.get("/", headers={"Host": "reset.example.com"})
    assert response.status_code == 200
    assert b"Reset Mailbox Password" in response.data

    response = client.get("/login", headers={"Host": "reset.example.com"})
    assert response.status_code == 404


def _csrf_token_from_response(client, path="/", host="reset.example.com"):
    response = client.get(path, headers={"Host": host})
    cookie_header = response.headers.get("Set-Cookie", "")
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("csrf_token="):
            return part.split("=", 1)[1]
    return None


def test_portal_request_rejects_other_domain_mailbox():
    db.init_db()
    db.upsert_reset_portal("example.com", True, "reset", "")
    client = app.test_client()

    csrf_token = _csrf_token_from_response(client)
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


def test_logo_upload_validation():
    db.init_db()
    db.upsert_reset_portal("example.com", True, "reset", "")

    conn = sqlite3.connect(_tmp.name)
    conn.execute(
        "INSERT OR IGNORE INTO users (email, password_hash, is_admin) VALUES (?, ?, 1)",
        ("admin@local", "not-used",),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO delegations (user_id, domain, permissions)
        SELECT id, 'example.com', '["dns"]' FROM users WHERE email = 'admin@local'
        """
    )
    conn.commit()
    conn.close()

    client = app.test_client()
    csrf_token = _csrf_token_from_response(client, path="/login", host="localhost")
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
    portal = db.get_reset_portal("example.com")
    assert portal["logo_filename"] == "logo.png"
