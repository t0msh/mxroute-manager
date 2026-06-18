"""Service-layer tests for deploy_missing_dns_to_cf (DNS fix button logic)."""
from unittest.mock import patch

import pytest

from services.cloudflare import deploy_missing_dns_to_cf

DOMAIN = "example.com"
ZONE_ID = "zone-fix-1"
EMPTY_DNS_SETS = (set(), set(), [])


def _health(*, on_mxroute=True, checks=None):
    checks = checks or {
        "verification": {"status": "fail", "label": "Verification"},
        "mx": {"status": "pass", "label": "MX"},
        "spf": {"status": "warn", "label": "SPF"},
        "dkim": {"status": "pending", "label": "DKIM"},
        "dmarc": {"status": "pass", "label": "DMARC"},
    }
    return {
        "domain": DOMAIN,
        "overall": "degraded",
        "on_mxroute": on_mxroute,
        "cf_configured": True,
        "checks": checks,
    }


def _fix_patches(health, *, deploy_side_effect=None):
    deploy_side_effect = deploy_side_effect or (lambda *a, **k: "added")
    return (
        patch("services.cloudflare.cf_is_configured", return_value=True),
        patch("services.cloudflare.build_setup_health", return_value=health),
        patch("services.cloudflare.ensure_cf_zone", return_value=ZONE_ID),
        patch("services.cloudflare.fetch_cf_dns_sets", return_value=EMPTY_DNS_SETS),
        patch("services.cloudflare.get_mxroute_verification_record", return_value={"name": "mxverify", "value": "x"}),
        patch("services.cloudflare.get_mxroute_dns_data", return_value={"mx_records": []}),
        patch("services.cloudflare.deploy_dns_record_to_cf", side_effect=deploy_side_effect),
        patch("services.cloudflare.audit"),
    )


def test_deploy_missing_dns_requires_cloudflare():
    with patch("services.cloudflare.cf_is_configured", return_value=False):
        with pytest.raises(ValueError, match="Cloudflare credentials"):
            deploy_missing_dns_to_cf(DOMAIN)


def test_deploy_missing_dns_requires_health():
    with patch("services.cloudflare.cf_is_configured", return_value=True), \
         patch("services.cloudflare.build_setup_health", return_value=None):
        with pytest.raises(ValueError, match="DNS health"):
            deploy_missing_dns_to_cf(DOMAIN)


def test_deploy_missing_dns_rejects_mail_records_before_mxroute_registration():
    health = _health(on_mxroute=False)
    patches = _fix_patches(health)
    with patches[0], patches[1], patches[6]:
        with pytest.raises(ValueError, match="registered on MXroute"):
            deploy_missing_dns_to_cf(DOMAIN, record_types=["mx"])


def test_deploy_missing_dns_returns_early_when_everything_passes():
    health = _health(checks={
        "verification": {"status": "pass"},
        "mx": {"status": "pass"},
        "spf": {"status": "pass"},
        "dkim": {"status": "pass"},
        "dmarc": {"status": "pass"},
    })
    with patch("services.cloudflare.cf_is_configured", return_value=True), \
         patch("services.cloudflare.build_setup_health", return_value=health), \
         patch("services.cloudflare.ensure_cf_zone") as mock_zone, \
         patch("services.cloudflare.audit"):
        result = deploy_missing_dns_to_cf(DOMAIN)

    assert result["fixed"] == []
    assert set(result["skipped"]) == set(health["checks"].keys())
    assert "already look good" in result["steps"][0].lower()
    mock_zone.assert_not_called()


def test_deploy_missing_dns_auto_selects_warn_and_fail_checks():
    health = _health()
    patches = _fix_patches(health)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6] as mock_deploy, patches[7]:
        result = deploy_missing_dns_to_cf(DOMAIN)

    deployed_types = [call.args[2] for call in mock_deploy.call_args_list]
    assert deployed_types == ["verification", "spf"]
    assert result["fixed"] == ["verification", "spf"]
    assert "mx" not in result["fixed"]
    assert "dkim" not in result["fixed"]


def test_deploy_missing_dns_honours_explicit_record_list():
    health = _health()
    patches = _fix_patches(health)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6] as mock_deploy, patches[7]:
        result = deploy_missing_dns_to_cf(DOMAIN, record_types=["verification", "MX"])

    assert mock_deploy.call_count == 1
    assert mock_deploy.call_args.args[2] == "verification"
    assert result["fixed"] == ["verification"]


def test_deploy_missing_dns_skips_records_already_passing():
    health = _health(checks={
        "verification": {"status": "pass"},
        "mx": {"status": "fail"},
        "spf": {"status": "pass"},
        "dkim": {"status": "pending"},
        "dmarc": {"status": "pass"},
    })
    patches = _fix_patches(health)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6] as mock_deploy, patches[7]:
        result = deploy_missing_dns_to_cf(DOMAIN, record_types=["verification", "mx", "spf", "dkim"])

    assert mock_deploy.call_count == 1
    assert mock_deploy.call_args.args[2] == "mx"
    assert result["fixed"] == ["mx"]
    assert "verification" in result["skipped"]
    assert "spf" in result["skipped"]
    assert "dkim" in result["skipped"]


def test_deploy_missing_dns_audits_when_records_fixed():
    health = _health(checks={"verification": {"status": "fail"}, "mx": {"status": "pass"}})
    patches = _fix_patches(health)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7] as mock_audit:
        deploy_missing_dns_to_cf(DOMAIN, record_types=["verification"])

    mock_audit.assert_called_once_with("dns.fix", target=DOMAIN, records=["verification"], outcome="updated")


def test_deploy_missing_dns_audits_no_changes_when_deploy_skips():
    health = _health(checks={"verification": {"status": "fail"}})
    patches = _fix_patches(health, deploy_side_effect=lambda *a, **k: "skipped")
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7] as mock_audit:
        result = deploy_missing_dns_to_cf(DOMAIN, record_types=["verification"])

    assert result["fixed"] == []
    assert result["skipped"] == ["verification"]
    mock_audit.assert_called_once_with("dns.fix", target=DOMAIN, records=[], outcome="no_changes")


def test_deploy_missing_dns_treats_updated_as_fixed():
    health = _health(checks={"spf": {"status": "warn"}})
    patches = _fix_patches(health, deploy_side_effect=lambda *a, **k: "updated")
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7] as mock_audit:
        result = deploy_missing_dns_to_cf(DOMAIN, record_types=["spf"])

    assert result["fixed"] == ["spf"]
    mock_audit.assert_called_once_with("dns.fix", target=DOMAIN, records=["spf"], outcome="updated")
