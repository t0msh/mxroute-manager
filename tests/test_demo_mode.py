"""Integration tests for DEMO_MODE simulated backends."""
import pytest

from services.cloudflare import cf_is_configured
from services.demo_backend import demo_mx_request_raw, reset_demo_state
from services.demo_mode import is_demo_mode
from services.mxroute import mx_request_raw
from tests.helpers import (
    auth_post_headers,
    insert_user_with_grants,
    prime_authenticated_session,
)


@pytest.fixture(autouse=True)
def demo_env(monkeypatch, db_connection):
    monkeypatch.setenv("DEMO_MODE", "true")
    reset_demo_state()
    db_connection.execute("DELETE FROM delegations")
    db_connection.execute("DELETE FROM users")
    db_connection.commit()
    yield
    reset_demo_state()


@pytest.fixture
def admin_token(fresh_db, client, db_connection):
    insert_user_with_grants(db_connection, "admin@local", is_admin=True)
    return prime_authenticated_session(client, "admin@local")


def test_is_demo_mode_enabled(demo_env):
    assert is_demo_mode() is True


def test_demo_quota_grace_period_compliant():
    res, status = demo_mx_request_raw("GET", "/quota")
    assert status == 200
    assert res["data"]["grace_period"] is None


def test_demo_reset_interval_defaults_to_ten_minutes(monkeypatch):
    monkeypatch.delenv("DEMO_RESET_MINUTES", raising=False)
    from services.demo_reset import demo_reset_interval_seconds

    assert demo_reset_interval_seconds() == 600


def test_reset_demo_instance_restores_seeded_mailboxes(db_connection):
    from models.db import set_recovery_email
    from services.demo_reset import reset_demo_instance

    demo_mx_request_raw(
        "POST",
        "/domains/example.com/email-accounts",
        {"username": "temp", "password": "x", "quota": 100, "limit": 50},
    )
    listed, _ = demo_mx_request_raw("GET", "/domains/example.com/email-accounts")
    assert "temp" in {item["username"] for item in listed["data"]}

    set_recovery_email("hello@example.com", "backup@example.com")

    reset_demo_instance()

    listed, _ = demo_mx_request_raw("GET", "/domains/example.com/email-accounts")
    usernames = {item["username"] for item in listed["data"]}
    assert "temp" not in usernames
    assert "hello" in usernames

    row = db_connection.execute(
        "SELECT COUNT(*) FROM mailbox_recovery WHERE mailbox_email = ?",
        ("hello@example.com",),
    ).fetchone()[0]
    assert row == 0


def test_demo_lists_fictional_domains():
    res, status = mx_request_raw("GET", "/domains")
    assert status == 200
    assert set(res["data"]) == {"example.com", "notarealsite.org", "demo.net"}


def test_demo_rejects_non_allowlist_domain():
    res, status = demo_mx_request_raw("POST", "/domains", {"domain": "evil.com"})
    assert status == 400
    assert "demo" in res["error"]["message"].lower()


def test_demo_creates_mailbox_without_real_api(fresh_db, client, admin_token):
    response = client.post(
        "/api/domains/example.com/email-accounts",
        headers=auth_post_headers(admin_token),
        json={"username": "demo", "password": "Abcd1234!", "quota": 512, "limit": 200},
    )
    assert response.status_code == 201

    listed, status = mx_request_raw("GET", "/domains/example.com/email-accounts")
    assert status == 200
    usernames = {item["username"] for item in listed["data"]}
    assert "demo" in usernames


def test_demo_cloudflare_reported_configured():
    assert cf_is_configured() is True


def test_demo_dns_health_healthy_for_seeded_domain():
    dns_res, dns_status = mx_request_raw("GET", "/domains/example.com/dns")
    assert dns_status == 200

    from services.dns_health import check_dns_health
    from services.mxroute import get_mxroute_verification_record

    health = check_dns_health(
        "example.com",
        dns_res["data"],
        verification_record=get_mxroute_verification_record(),
    )
    assert health["overall"] == "healthy"


def test_demo_cloudflare_setup_simulated(fresh_db, client, admin_token):
    response = client.post(
        "/api/cloudflare/setup",
        headers=auth_post_headers(admin_token),
        json={"domain": "demo.net"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert any("complete" in step.lower() for step in payload["steps"])

    dns_res, _ = mx_request_raw("GET", "/domains/demo.net/dns")
    from services.dns_health import check_dns_health
    from services.mxroute import get_mxroute_verification_record

    health = check_dns_health(
        "demo.net",
        dns_res["data"],
        verification_record=get_mxroute_verification_record(),
    )
    assert health["overall"] == "healthy"
