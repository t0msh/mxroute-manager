"""Tests for public DNS health comparison logic (no live DNS lookups)."""
from unittest.mock import patch

from services.dns_health import (
    apply_mail_hosting_context,
    check_dns_health,
    dkim_record_parts,
    overall_from_checks,
)


def test_overall_from_checks_unhealthy_when_any_fail():
    checks = {
        "mx": {"status": "pass"},
        "spf": {"status": "fail"},
    }
    assert overall_from_checks(checks) == "unhealthy"


def test_overall_from_checks_degraded_when_warn_only():
    checks = {
        "mx": {"status": "pass"},
        "dkim": {"status": "warn"},
    }
    assert overall_from_checks(checks) == "degraded"


def test_apply_mail_hosting_context_skips_mail_checks():
    health = {
        "checks": {
            "mx": {"status": "fail", "message": "bad"},
            "spf": {"status": "fail", "message": "bad"},
            "verification": {"status": "pass", "message": "ok"},
        },
        "overall": "unhealthy",
    }
    result = apply_mail_hosting_context(health, mail_hosting_enabled=False)

    assert result["checks"]["mx"]["status"] == "skipped"
    assert result["checks"]["spf"]["status"] == "skipped"
    assert result["checks"]["verification"]["status"] == "pass"
    assert result["overall"] == "healthy"


def test_dkim_record_parts_relative_host():
    host_part, fqdn = dkim_record_parts({"name": "x._domainkey"}, "example.com")
    assert host_part == "x._domainkey"
    assert fqdn == "x._domainkey.example.com"


def test_check_dns_health_passes_when_public_dns_matches():
    expected = {
        "mx_records": [{"hostname": "mail.mxroute.com", "priority": 10}],
        "spf": {"value": "v=spf1 include:mxroute.com ~all"},
        "dkim": {"name": "x._domainkey", "value": "v=DKIM1; k=rsa; p=abc123"},
    }
    verify = {"name": "mxverify", "value": "mxroute-verify=token"}

    with patch("services.dns_health._query_mx", return_value=[
        {"hostname": "mail.mxroute.com", "priority": 10},
    ]), patch("services.dns_health._query_txt") as mock_txt:
        mock_txt.side_effect = lambda name: {
            "example.com": ['v=spf1 include:mxroute.com ~all'],
            "x._domainkey.example.com": ["v=DKIM1; k=rsa; p=abc123"],
            "_dmarc.example.com": ["v=DMARC1; p=none; sp=none; adkim=r; aspf=r;"],
            "mxverify.example.com": ["mxroute-verify=token"],
        }.get(name, [])

        health = check_dns_health(
            "example.com",
            expected,
            verification_record=verify,
            dmarc_expected="v=DMARC1; p=none; sp=none; adkim=r; aspf=r;",
        )

    assert health["checks"]["mx"]["status"] == "pass"
    assert health["checks"]["spf"]["status"] == "pass"
    assert health["checks"]["dkim"]["status"] == "pass"
    assert health["checks"]["verification"]["status"] == "pass"
    assert health["overall"] == "healthy"


def test_check_dns_health_fails_mx_mismatch():
    expected = {"mx_records": [{"hostname": "mail.mxroute.com", "priority": 10}]}

    with patch("services.dns_health._query_mx", return_value=[
        {"hostname": "wrong.mail.com", "priority": 20},
    ]), patch("services.dns_health._query_txt", return_value=[]):
        health = check_dns_health("example.com", expected)

    assert health["checks"]["mx"]["status"] == "fail"
    assert health["overall"] == "unhealthy"
