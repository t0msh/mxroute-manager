"""Tests that domain/DNS setup routines are idempotent (read-before-write)."""

from unittest.mock import patch

from services.cloudflare import (
    cf_upsert_txt,
    cf_upsert_cname,
    ensure_cf_zone,
    deploy_dns_record_to_cf,
)
from services.mxroute import register_domain_on_mxroute


def test_cf_upsert_txt_skips_when_content_matches():
    fqdn = "verify.example.com"
    content = "mxroute-verify=abc123"
    existing_records = [
        {
            "id": "rec-1",
            "type": "TXT",
            "name": fqdn,
            "content": content,
        }
    ]
    existing_txt = {(fqdn, content)}

    with patch("services.cloudflare.cf_request") as mock_cf:
        result = cf_upsert_txt(
            "zone-1",
            "verify",
            fqdn,
            content,
            existing_records,
            existing_txt,
            steps=None,
            log_messages={"skipped": "skip", "added": "add", "updated": "upd"},
        )

    assert result == "skipped"
    mock_cf.assert_not_called()


def test_cf_upsert_txt_posts_when_missing():
    fqdn = "verify.example.com"
    content = "mxroute-verify=abc123"

    with patch(
        "services.cloudflare.cf_request", return_value={"success": True}
    ) as mock_cf:
        result = cf_upsert_txt(
            "zone-1",
            "verify",
            fqdn,
            content,
            [],
            set(),
            steps=None,
            log_messages={"skipped": "skip", "added": "add", "updated": "upd"},
        )

    assert result == "added"
    mock_cf.assert_called_once()
    assert mock_cf.call_args[0][0] == "POST"


def test_cf_upsert_cname_skips_when_target_matches():
    fqdn = "reset.example.com"
    target = "manager.example.com"
    existing_records = [
        {
            "id": "rec-1",
            "type": "CNAME",
            "name": fqdn,
            "content": target,
            "proxied": True,
        }
    ]

    with patch("services.cloudflare.cf_request") as mock_cf:
        result = cf_upsert_cname(
            "zone-1",
            "reset",
            fqdn,
            target,
            existing_records,
            steps=None,
            proxied=True,
        )

    assert result == "skipped"
    mock_cf.assert_not_called()


def test_ensure_cf_zone_reuses_existing_zone():
    with (
        patch("services.cloudflare.find_cf_zone_id", return_value="zone-existing"),
        patch("services.cloudflare.cf_request") as mock_cf,
        patch("services.cloudflare.get_config_value", return_value="acct-1"),
    ):
        zone_id = ensure_cf_zone("example.com", steps=[])

    assert zone_id == "zone-existing"
    mock_cf.assert_not_called()


def test_register_domain_on_mxroute_skips_when_present():
    with (
        patch("services.mxroute.domain_on_mxroute", return_value=True),
        patch("services.mxroute.mx_request_raw") as mock_mx,
    ):
        result = register_domain_on_mxroute("example.com", steps=[])

    assert result == "skipped"
    mock_mx.assert_not_called()


def test_register_domain_on_mxroute_creates_when_missing():
    with (
        patch("services.mxroute.domain_on_mxroute", return_value=False),
        patch("services.mxroute.mx_request_raw", return_value=({"success": True}, 201)),
        patch("services.mxroute.audit"),
    ):
        result = register_domain_on_mxroute("example.com", steps=[])

    assert result == "added"


def test_deploy_mx_records_skips_when_already_present():
    domain = "example.com"
    mx_dns_data = {
        "mx_records": [{"hostname": "mail.example.com", "priority": 10}],
    }
    existing_mx = {(domain, "mail.example.com", 10)}

    with patch("services.cloudflare.cf_request") as mock_cf:
        result = deploy_dns_record_to_cf(
            domain,
            "zone-1",
            "mx",
            mx_dns_data,
            None,
            existing_mx,
            set(),
            [],
            steps=[],
        )

    assert result == "skipped"
    mock_cf.assert_not_called()
