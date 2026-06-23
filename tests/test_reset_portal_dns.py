"""Tests for reset portal DNS status checks."""

from unittest.mock import MagicMock, patch

import dns.resolver

from services.cloudflare import check_reset_portal_dns

CNAME_TARGET = "mxtools.t0m.sh"

PORTAL = {
    "domain": "wanky.wang",
    "enabled": True,
    "subdomain_prefix": "reset",
    "portal_host": "reset.wanky.wang",
}


def test_dns_check_uses_cloudflare_api_for_proxied_cname():
    records = [
        {
            "type": "CNAME",
            "name": "reset.wanky.wang",
            "content": "mxtools.t0m.sh",
            "proxied": True,
        }
    ]
    with (
        patch(
            "services.cloudflare_portal.get_reset_portal_cname_target",
            return_value=CNAME_TARGET,
        ),
        patch("services.cloudflare_portal.cf_is_configured", return_value=True),
        patch("services.cloudflare_portal.find_cf_zone_id", return_value="zone-1"),
        patch(
            "services.cloudflare_portal.fetch_cf_dns_sets",
            return_value=(set(), set(), records),
        ),
        patch("services.cloudflare_portal.public_dns_resolves", return_value=True),
    ):
        result = check_reset_portal_dns(PORTAL)

    assert result["status"] == "pass"
    assert result["source"] == "cloudflare"
    assert "proxied" in result["message"]


def test_dns_check_warns_when_cf_record_exists_but_public_dns_missing():
    records = [
        {
            "type": "CNAME",
            "name": "reset.wanky.wang",
            "content": "mxtools.t0m.sh",
            "proxied": True,
        }
    ]
    with (
        patch(
            "services.cloudflare_portal.get_reset_portal_cname_target",
            return_value=CNAME_TARGET,
        ),
        patch("services.cloudflare_portal.cf_is_configured", return_value=True),
        patch("services.cloudflare_portal.find_cf_zone_id", return_value="zone-1"),
        patch(
            "services.cloudflare_portal.fetch_cf_dns_sets",
            return_value=(set(), set(), records),
        ),
        patch("services.cloudflare_portal.public_dns_resolves", return_value=False),
    ):
        result = check_reset_portal_dns(PORTAL)

    assert result["status"] == "warn"
    assert "nameservers" in result["message"].lower()


def test_dns_check_accepts_public_a_record_when_cname_hidden():
    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = dns.resolver.NoAnswer()

    with (
        patch(
            "services.cloudflare_portal.get_reset_portal_cname_target",
            return_value=CNAME_TARGET,
        ),
        patch("services.cloudflare_portal.cf_is_configured", return_value=False),
        patch("services.cloudflare_portal.public_dns_resolves", return_value=True),
        patch("dns.resolver.Resolver", return_value=mock_resolver),
    ):
        result = check_reset_portal_dns(PORTAL)

    assert result["status"] == "pass"
    assert result["source"] == "public"
