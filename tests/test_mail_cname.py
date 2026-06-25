"""Tests for mail.<domain> CNAME deploy and health check."""

from unittest.mock import patch

import pytest

from services.cloudflare import (
    CfDeployContext,
    deploy_dns_record_to_cf,
    _mail_health_check,
)
from tests.helpers import (
    auth_post_headers,
    insert_user_with_grants,
    prime_authenticated_session,
)

DOMAIN = "example.com"
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


def test_mail_deploy_uses_mx_server_target_unproxied():
    with (
        patch("models.db.get_config_value", return_value=MX_SERVER),
        patch(
            "services.cloudflare_deploy.cf_upsert_cname", return_value="added"
        ) as mock_cname,
    ):
        ctx = CfDeployContext(DOMAIN, "zone1", None, None, set(), set(), [], steps=[])
        result = deploy_dns_record_to_cf(ctx, "mail")

    assert result == "added"
    mock_cname.assert_called_once()
    args, kwargs = mock_cname.call_args
    assert args[1] == "mail"
    assert args[2] == f"mail.{DOMAIN}"
    assert args[3] == MX_SERVER
    assert kwargs.get("proxied") is False


def test_mail_deploy_skipped_without_mx_server():
    with (
        patch("models.db.get_config_value", return_value=""),
        patch("services.cloudflare_deploy.cf_upsert_cname") as mock_cname,
    ):
        ctx = CfDeployContext(DOMAIN, "zone1", None, None, set(), set(), [], steps=[])
        result = deploy_dns_record_to_cf(ctx, "mail")

    assert result == "skipped"
    mock_cname.assert_not_called()


def test_mail_health_skipped_without_mx_server():
    with patch("models.db.get_config_value", return_value=""):
        assert _mail_health_check(DOMAIN)["status"] == "skipped"


def test_mail_health_fail_when_not_deployed():
    with (
        patch("models.db.get_config_value", return_value=MX_SERVER),
        patch("services.cloudflare_health.find_cf_zone_id", return_value="zone1"),
        patch(
            "services.cloudflare_health.fetch_cf_dns_sets",
            return_value=(set(), set(), []),
        ),
        patch("services.cloudflare_health._query_cname_target", return_value=None),
    ):
        assert _mail_health_check(DOMAIN)["status"] == "fail"


def test_mail_health_pending_when_in_cf_not_resolving():
    records = [{"type": "CNAME", "name": f"mail.{DOMAIN}", "content": MX_SERVER}]
    with (
        patch("models.db.get_config_value", return_value=MX_SERVER),
        patch("services.cloudflare_health.find_cf_zone_id", return_value="zone1"),
        patch(
            "services.cloudflare_health.fetch_cf_dns_sets",
            return_value=(set(), set(), records),
        ),
        patch("services.cloudflare_health._query_cname_target", return_value=None),
        patch("services.cloudflare_health.public_dns_resolves", return_value=False),
    ):
        assert _mail_health_check(DOMAIN)["status"] == "pending"


def test_mail_health_pass_when_resolving():
    records = [{"type": "CNAME", "name": f"mail.{DOMAIN}", "content": MX_SERVER}]
    with (
        patch("models.db.get_config_value", return_value=MX_SERVER),
        patch("services.cloudflare_health.find_cf_zone_id", return_value="zone1"),
        patch(
            "services.cloudflare_health.fetch_cf_dns_sets",
            return_value=(set(), set(), records),
        ),
        patch("services.cloudflare_health._query_cname_target", return_value=MX_SERVER),
    ):
        check = _mail_health_check(DOMAIN)
    assert check["status"] == "pass"
    assert check["found"] == [MX_SERVER]


def test_mail_deploy_included_in_setup_wizard_fix(fresh_db, client, admin_token):
    fix_result = {"fixed": ["mail"], "skipped": [], "steps": ["done"]}
    with (
        patch("routes.cloudflare.cf_is_configured", return_value=True),
        patch(
            "routes.cloudflare.deploy_missing_dns_to_cf", return_value=fix_result
        ) as mock_fix,
    ):
        response = client.post(
            f"/api/domains/{DOMAIN}/dns/fix",
            headers=auth_post_headers(admin_token),
            json={"records": ["mail"]},
        )

    assert response.status_code == 200
    mock_fix.assert_called_once_with(DOMAIN, ["mail"])
