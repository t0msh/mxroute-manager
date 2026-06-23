"""Functional + security tests for the webmail CNAME deploy and health check.

Webmail deploy reuses POST /api/domains/<domain>/dns/fix, so these tests verify
both the Cloudflare wiring (fixed MX_SERVER target, unproxied) and that the
existing authorization/CSRF trust boundary still holds for the new action.
"""

from unittest.mock import patch

import pytest

from services.cloudflare import CfDeployContext, deploy_dns_record_to_cf, _webmail_health_check
from tests.helpers import (
    auth_post_headers,
    insert_user_with_grants,
    prime_authenticated_session,
)

DOMAIN = "example.com"
OTHER_DOMAIN = "not-yours.com"
MX_SERVER = "yourmxserver.mxrouting.net"


@pytest.fixture(autouse=True)
def clear_tables(db_connection):
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


@pytest.fixture
def emails_delegate_token(fresh_db, client, db_connection):
    insert_user_with_grants(
        db_connection,
        "emails@local",
        grants=[{"domain": DOMAIN, "permissions": ["emails"]}],
    )
    return prime_authenticated_session(client, "emails@local")


# --- Functional: Cloudflare wiring ---


def test_webmail_deploy_uses_mx_server_target_unproxied():
    with (
        patch("models.db.get_config_value", return_value=MX_SERVER),
        patch(
            "services.cloudflare_deploy.cf_upsert_cname", return_value="added"
        ) as mock_cname,
    ):
        ctx = CfDeployContext(DOMAIN, "zone1", None, None, set(), set(), [], steps=[])
        result = deploy_dns_record_to_cf(ctx, "webmail")

    assert result == "added"
    mock_cname.assert_called_once()
    args, kwargs = mock_cname.call_args
    assert args[1] == "webmail"
    assert args[2] == f"webmail.{DOMAIN}"
    # Target is the configured server only — never caller-controlled.
    assert args[3] == MX_SERVER
    assert kwargs.get("proxied") is False


def test_webmail_deploy_skipped_without_mx_server():
    with (
        patch("models.db.get_config_value", return_value=""),
        patch("services.cloudflare_deploy.cf_upsert_cname") as mock_cname,
    ):
        ctx = CfDeployContext(DOMAIN, "zone1", None, None, set(), set(), [], steps=[])
        result = deploy_dns_record_to_cf(ctx, "webmail")

    assert result == "skipped"
    mock_cname.assert_not_called()


# --- Functional: health states ---


def test_webmail_health_skipped_without_mx_server():
    with patch("models.db.get_config_value", return_value=""):
        assert _webmail_health_check(DOMAIN)["status"] == "skipped"


def test_webmail_health_skipped_when_not_deployed():
    with (
        patch("models.db.get_config_value", return_value=MX_SERVER),
        patch("services.cloudflare_health.find_cf_zone_id", return_value="zone1"),
        patch(
            "services.cloudflare_health.fetch_cf_dns_sets",
            return_value=(set(), set(), []),
        ),
    ):
        assert _webmail_health_check(DOMAIN)["status"] == "skipped"


def test_webmail_health_pending_when_in_cf_not_resolving():
    records = [{"type": "CNAME", "name": f"webmail.{DOMAIN}", "content": MX_SERVER}]
    with (
        patch("models.db.get_config_value", return_value=MX_SERVER),
        patch("services.cloudflare_health.find_cf_zone_id", return_value="zone1"),
        patch(
            "services.cloudflare_health.fetch_cf_dns_sets",
            return_value=(set(), set(), records),
        ),
        patch("services.cloudflare_health.public_dns_resolves", return_value=False),
    ):
        assert _webmail_health_check(DOMAIN)["status"] == "pending"


def test_webmail_health_pass_when_resolving():
    records = [{"type": "CNAME", "name": f"webmail.{DOMAIN}", "content": MX_SERVER}]
    with (
        patch("models.db.get_config_value", return_value=MX_SERVER),
        patch("services.cloudflare_health.find_cf_zone_id", return_value="zone1"),
        patch(
            "services.cloudflare_health.fetch_cf_dns_sets",
            return_value=(set(), set(), records),
        ),
        patch("services.cloudflare_health.public_dns_resolves", return_value=True),
    ):
        check = _webmail_health_check(DOMAIN)
    assert check["status"] == "pass"
    assert check["found"] == [MX_SERVER]


# --- Security: authorization, scoping, CSRF, validation ---


def test_webmail_deploy_allowed_for_admin(fresh_db, client, admin_token):
    fix_result = {"fixed": ["webmail"], "skipped": [], "steps": ["done"]}
    with (
        patch("routes.cloudflare.cf_is_configured", return_value=True),
        patch(
            "routes.cloudflare.deploy_missing_dns_to_cf", return_value=fix_result
        ) as mock_fix,
    ):
        response = client.post(
            f"/api/domains/{DOMAIN}/dns/fix",
            headers=auth_post_headers(admin_token),
            json={"records": ["webmail"]},
        )

    assert response.status_code == 200
    mock_fix.assert_called_once_with(DOMAIN, ["webmail"])


def test_webmail_deploy_allowed_for_dns_delegate(fresh_db, client, dns_delegate_token):
    fix_result = {"fixed": ["webmail"], "skipped": [], "steps": ["done"]}
    with (
        patch("routes.cloudflare.cf_is_configured", return_value=True),
        patch("routes.cloudflare.deploy_missing_dns_to_cf", return_value=fix_result),
    ):
        response = client.post(
            f"/api/domains/{DOMAIN}/dns/fix",
            headers=auth_post_headers(dns_delegate_token),
            json={"records": ["webmail"]},
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["fixed"] == ["webmail"]


def test_webmail_deploy_blocked_cross_domain(fresh_db, client, dns_delegate_token):
    """A dns delegate for DOMAIN cannot deploy webmail for a different domain."""
    with (
        patch("routes.cloudflare.cf_is_configured", return_value=True),
        patch("routes.cloudflare.deploy_missing_dns_to_cf") as mock_fix,
    ):
        response = client.post(
            f"/api/domains/{OTHER_DOMAIN}/dns/fix",
            headers=auth_post_headers(dns_delegate_token),
            json={"records": ["webmail"]},
        )

    assert response.status_code == 403
    mock_fix.assert_not_called()


def test_webmail_deploy_blocked_for_emails_delegate(
    fresh_db, client, emails_delegate_token
):
    with (
        patch("routes.cloudflare.cf_is_configured", return_value=True),
        patch("routes.cloudflare.deploy_missing_dns_to_cf") as mock_fix,
    ):
        response = client.post(
            f"/api/domains/{DOMAIN}/dns/fix",
            headers=auth_post_headers(emails_delegate_token),
            json={"records": ["webmail"]},
        )

    assert response.status_code == 403
    mock_fix.assert_not_called()


def test_webmail_deploy_requires_csrf(fresh_db, client, admin_token):
    with (
        patch("routes.cloudflare.cf_is_configured", return_value=True),
        patch("routes.cloudflare.deploy_missing_dns_to_cf") as mock_fix,
    ):
        response = client.post(
            f"/api/domains/{DOMAIN}/dns/fix",
            json={"records": ["webmail"]},
        )

    assert response.status_code == 400
    assert "csrf" in response.get_json()["error"]["message"].lower()
    mock_fix.assert_not_called()


def test_webmail_deploy_rejects_invalid_domain(fresh_db, client, admin_token):
    with (
        patch("routes.cloudflare.cf_is_configured", return_value=True),
        patch("routes.cloudflare.deploy_missing_dns_to_cf") as mock_fix,
    ):
        response = client.post(
            "/api/domains/invalid/dns/fix",
            headers=auth_post_headers(admin_token),
            json={"records": ["webmail"]},
        )

    assert response.status_code == 400
    mock_fix.assert_not_called()
