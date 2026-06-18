"""HTTP tests for the Domain & DNS Cloudflare setup wizard."""
from unittest.mock import patch

import pytest

from tests.helpers import (
    auth_post_headers,
    insert_user_with_grants,
    prime_authenticated_session,
)

DOMAIN = "example.com"
ZONE_ID = "zone-abc123"
VERIFY_RECORD = {"name": "mxverify", "value": "mxroute-verify=abc123"}
MX_DNS_DATA = {
    "mx_records": [{"hostname": "mail.mxroute.com", "priority": 10}],
    "spf": {"value": "v=spf1 include:mxroute.com ~all"},
    "dkim": {"name": "default._domainkey", "value": "v=DKIM1; k=rsa; p=abc"},
    "dmarc": {"name": "_dmarc", "value": "v=DMARC1; p=none"},
}
EMPTY_DNS_SETS = (set(), set(), [])


@pytest.fixture(autouse=True)
def clear_wizard_tables(db_connection):
    db_connection.execute("DELETE FROM delegations")
    db_connection.execute("DELETE FROM users")
    db_connection.commit()


@pytest.fixture
def admin_token(fresh_db, client, db_connection):
    insert_user_with_grants(db_connection, "admin@local", is_admin=True)
    return prime_authenticated_session(client, "admin@local")


@pytest.fixture
def dns_delegate_token(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "dns@local",
        grants=[{"domain": DOMAIN, "permissions": ["dns"]}],
    )
    return prime_authenticated_session(client, "dns@local")


def _wizard_patches(*, register_result="added", deploy_result="added"):
    return (
        patch("routes.cloudflare.ensure_cf_zone", return_value=ZONE_ID),
        patch("routes.cloudflare.get_mxroute_verification_record", return_value=VERIFY_RECORD),
        patch("routes.cloudflare.fetch_cf_dns_sets", return_value=EMPTY_DNS_SETS),
        patch("routes.cloudflare.deploy_dns_record_to_cf", return_value=deploy_result),
        patch("routes.cloudflare.register_domain_on_mxroute", return_value=register_result),
        patch("routes.cloudflare.get_mxroute_dns_data", return_value=MX_DNS_DATA),
        patch("routes.cloudflare.audit"),
    )


def test_cf_status_requires_admin(fresh_db, client, dns_delegate_token):
    response = client.get("/api/cloudflare/status")
    assert response.status_code == 403


def test_cf_status_reports_configured(fresh_db, client, admin_token):
    response = client.get("/api/cloudflare/status")
    assert response.status_code == 200
    assert response.get_json()["configured"] is True


def test_cf_setup_requires_admin(fresh_db, client, dns_delegate_token):
    response = client.post(
        "/api/cloudflare/setup",
        headers=auth_post_headers(dns_delegate_token),
        json={"domain": DOMAIN},
    )
    assert response.status_code == 403


def test_cf_setup_requires_csrf(fresh_db, client, admin_token):
    with patch("routes.cloudflare.cf_is_configured", return_value=True), \
         patch("routes.cloudflare.ensure_cf_zone") as mock_zone:
        response = client.post("/api/cloudflare/setup", json={"domain": DOMAIN})

    assert response.status_code == 400
    assert "csrf" in response.get_json()["error"]["message"].lower()
    mock_zone.assert_not_called()


def test_cf_setup_rejects_invalid_domain(fresh_db, client, admin_token):
    with patch("routes.cloudflare.cf_is_configured", return_value=True), \
         patch("routes.cloudflare.ensure_cf_zone") as mock_zone:
        response = client.post(
            "/api/cloudflare/setup",
            headers=auth_post_headers(admin_token),
            json={"domain": "not valid"},
        )

    assert response.status_code == 400
    mock_zone.assert_not_called()


def test_cf_setup_requires_cloudflare_credentials(fresh_db, client, admin_token):
    with patch("routes.cloudflare.cf_is_configured", return_value=False), \
         patch("routes.cloudflare.ensure_cf_zone") as mock_zone:
        response = client.post(
            "/api/cloudflare/setup",
            headers=auth_post_headers(admin_token),
            json={"domain": DOMAIN},
        )

    assert response.status_code == 400
    assert "cloudflare" in response.get_json()["error"]["message"].lower()
    mock_zone.assert_not_called()


def test_cf_setup_happy_path(fresh_db, client, admin_token):
    patches = _wizard_patches()
    with patches[0], patches[1], patches[2], patches[3] as mock_deploy, patches[4] as mock_register, patches[5], patches[6] as mock_audit:
        response = client.post(
            "/api/cloudflare/setup",
            headers=auth_post_headers(admin_token),
            json={"domain": DOMAIN},
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert any("complete" in step.lower() for step in payload["steps"])
    mock_register.assert_called_once()
    assert mock_deploy.call_count == 5  # verification + mx, spf, dkim, dmarc
    mock_audit.assert_called_once_with("cloudflare.setup", target=DOMAIN, steps=len(payload["steps"]))


def test_cf_setup_succeeds_when_mxroute_already_registered(fresh_db, client, admin_token):
    patches = _wizard_patches(register_result="skipped", deploy_result="skipped")
    with patches[0], patches[1], patches[2], patches[3], patches[4] as mock_register, patches[5], patches[6]:
        response = client.post(
            "/api/cloudflare/setup",
            headers=auth_post_headers(admin_token),
            json={"domain": DOMAIN},
        )

    assert response.status_code == 200
    mock_register.assert_called_once()


def test_cf_setup_fails_without_verification_key(fresh_db, client, admin_token):
    with patch("routes.cloudflare.cf_is_configured", return_value=True), \
         patch("routes.cloudflare.ensure_cf_zone", return_value=ZONE_ID), \
         patch("routes.cloudflare.get_mxroute_verification_record", return_value=None), \
         patch("routes.cloudflare.register_domain_on_mxroute") as mock_register:
        response = client.post(
            "/api/cloudflare/setup",
            headers=auth_post_headers(admin_token),
            json={"domain": DOMAIN},
        )

    assert response.status_code == 500
    assert "verification" in response.get_json()["error"]["message"].lower()
    mock_register.assert_not_called()


def test_cf_setup_fails_without_mx_dns_data(fresh_db, client, admin_token):
    with patch("routes.cloudflare.cf_is_configured", return_value=True), \
         patch("routes.cloudflare.ensure_cf_zone", return_value=ZONE_ID), \
         patch("routes.cloudflare.get_mxroute_verification_record", return_value=VERIFY_RECORD), \
         patch("routes.cloudflare.fetch_cf_dns_sets", return_value=EMPTY_DNS_SETS), \
         patch("routes.cloudflare.deploy_dns_record_to_cf", return_value="added"), \
         patch("routes.cloudflare.register_domain_on_mxroute", return_value="added"), \
         patch("routes.cloudflare.get_mxroute_dns_data", return_value=None):
        response = client.post(
            "/api/cloudflare/setup",
            headers=auth_post_headers(admin_token),
            json={"domain": DOMAIN},
        )

    assert response.status_code == 500
    assert "mxroute dns" in response.get_json()["error"]["message"].lower()


def test_setup_health_requires_admin(fresh_db, client, dns_delegate_token):
    response = client.get(f"/api/domains/{DOMAIN}/dns/setup-health")
    assert response.status_code == 403


def test_setup_health_returns_wizard_state(fresh_db, client, admin_token):
    health = {
        "domain": DOMAIN,
        "overall": "degraded",
        "on_mxroute": False,
        "cf_configured": True,
        "checks": {"verification": {"status": "fail"}},
    }
    with patch("routes.cloudflare.build_setup_health", return_value=health):
        response = client.get(f"/api/domains/{DOMAIN}/dns/setup-health")

    assert response.status_code == 200
    assert response.get_json()["data"]["on_mxroute"] is False


def test_dns_fix_deploys_selected_records(fresh_db, client, admin_token):
    fix_result = {
        "fixed": ["verification", "mx"],
        "skipped": ["spf"],
        "steps": ["Fetching existing DNS records from Cloudflare..."],
    }
    with patch("routes.cloudflare.cf_is_configured", return_value=True), \
         patch("routes.cloudflare.deploy_missing_dns_to_cf", return_value=fix_result) as mock_fix:
        response = client.post(
            f"/api/domains/{DOMAIN}/dns/fix",
            headers=auth_post_headers(admin_token),
            json={"records": ["verification", "mx"]},
        )

    assert response.status_code == 200
    mock_fix.assert_called_once_with(DOMAIN, ["verification", "mx"])
    assert response.get_json()["data"]["fixed"] == ["verification", "mx"]


def test_dns_fix_requires_cloudflare(fresh_db, client, admin_token):
    with patch("routes.cloudflare.cf_is_configured", return_value=False), \
         patch("routes.cloudflare.deploy_missing_dns_to_cf") as mock_fix:
        response = client.post(
            f"/api/domains/{DOMAIN}/dns/fix",
            headers=auth_post_headers(admin_token),
            json={"records": ["mx"]},
        )

    assert response.status_code == 400
    mock_fix.assert_not_called()


def test_dns_delegate_can_read_health(fresh_db, client, dns_delegate_token):
    mx_dns = {"success": True, "data": MX_DNS_DATA}
    verify = {"success": True, "data": {"record": VERIFY_RECORD}}
    domains = {"success": True, "data": [DOMAIN]}

    def mx_raw_side_effect(method, path, payload=None):
        if path == f"/domains/{DOMAIN}/dns":
            return mx_dns, 200
        if path == "/verification-key":
            return verify, 200
        if path == "/domains":
            return domains, 200
        if path == f"/domains/{DOMAIN}":
            return {"success": True, "data": {"mail_hosting": True}}, 200
        return {"success": False}, 404

    with patch("routes.cloudflare.mx_request_raw", side_effect=mx_raw_side_effect), \
         patch("services.dns_health._query_mx", return_value=[]), \
         patch("services.dns_health._query_txt", return_value=[]):
        response = client.get(f"/api/domains/{DOMAIN}/dns/health")

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert "checks" in response.get_json()["data"]


def test_emails_only_delegate_cannot_read_dns_health(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "emails@local",
        grants=[{"domain": DOMAIN, "permissions": ["emails"]}],
    )
    prime_authenticated_session(client, "emails@local")

    with patch("routes.cloudflare.mx_request_raw") as mock_mx:
        response = client.get(f"/api/domains/{DOMAIN}/dns/health")

    assert response.status_code == 403
    mock_mx.assert_not_called()
