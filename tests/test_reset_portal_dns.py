"""Tests for reset portal DNS status checks."""
import os
import sys
import tempfile
from unittest.mock import patch

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_FILE"] = _tmp.name
os.environ["RESET_PORTAL_CNAME_TARGET"] = "mxtools.t0m.sh"
os.environ["CF_API_TOKEN"] = "cf-token"
os.environ["CF_ACCOUNT_ID"] = "cf-account"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.cloudflare import check_reset_portal_dns  # noqa: E402

CNAME_TARGET = "mxtools.t0m.sh"


PORTAL = {
    "domain": "wanky.wang",
    "enabled": True,
    "subdomain_prefix": "reset",
    "portal_host": "reset.wanky.wang",
}


def test_dns_check_uses_cloudflare_api_for_proxied_cname():
    records = [{
        "type": "CNAME",
        "name": "reset.wanky.wang",
        "content": "mxtools.t0m.sh",
        "proxied": True,
    }]
    with patch("models.db.get_reset_portal_cname_target", return_value=CNAME_TARGET), \
         patch("services.cloudflare.cf_is_configured", return_value=True), \
         patch("services.cloudflare.find_cf_zone_id", return_value="zone-1"), \
         patch("services.cloudflare.fetch_cf_dns_sets", return_value=(set(), set(), records)), \
         patch("services.cloudflare._public_dns_resolves", return_value=True):
        result = check_reset_portal_dns(PORTAL)

    assert result["status"] == "pass"
    assert result["source"] == "cloudflare"
    assert "proxied" in result["message"]


def test_dns_check_warns_when_cf_record_exists_but_public_dns_missing():
    records = [{
        "type": "CNAME",
        "name": "reset.wanky.wang",
        "content": "mxtools.t0m.sh",
        "proxied": True,
    }]
    with patch("models.db.get_reset_portal_cname_target", return_value=CNAME_TARGET), \
         patch("services.cloudflare.cf_is_configured", return_value=True), \
         patch("services.cloudflare.find_cf_zone_id", return_value="zone-1"), \
         patch("services.cloudflare.fetch_cf_dns_sets", return_value=(set(), set(), records)), \
         patch("services.cloudflare._public_dns_resolves", return_value=False):
        result = check_reset_portal_dns(PORTAL)

    assert result["status"] == "warn"
    assert "nameservers" in result["message"].lower()


def test_dns_check_accepts_public_a_record_when_cname_hidden():
    import dns.resolver
    from unittest.mock import MagicMock

    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = dns.resolver.NoAnswer()

    with patch("models.db.get_reset_portal_cname_target", return_value=CNAME_TARGET), \
         patch("services.cloudflare.cf_is_configured", return_value=False), \
         patch("services.cloudflare._public_dns_resolves", return_value=True), \
         patch("dns.resolver.Resolver", return_value=mock_resolver):
        result = check_reset_portal_dns(PORTAL)

    assert result["status"] == "pass"
    assert result["source"] == "public"
