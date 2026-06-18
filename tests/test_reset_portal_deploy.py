"""Tests for NPM + full reset portal deploy orchestration."""
import os
import sys
import tempfile
from unittest.mock import patch

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_FILE"] = _tmp.name
os.environ["RESET_PORTAL_CNAME_TARGET"] = "mxtools.t0m.sh"
os.environ["NPM_API_URL"] = "https://npm.example.com"
os.environ["NPM_IDENTITY"] = "admin@example.com"
os.environ["NPM_SECRET"] = "secret"
os.environ["NPM_FORWARD_HOST"] = "192.168.68.150"
os.environ["NPM_FORWARD_PORT"] = "5000"
os.environ["CF_API_TOKEN"] = "cf-token"
os.environ["CF_ACCOUNT_ID"] = "cf-account"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db  # noqa: E402
from services.npm import npm_is_configured  # noqa: E402
from services.reset_portal_deploy import (  # noqa: E402
    missing_deploy_config,
    reset_portal_deploy_is_configured,
    deploy_reset_portal,
    teardown_reset_portal,
    _friendly_https_error,
)


def test_npm_is_configured():
    assert npm_is_configured() is True


def test_missing_deploy_config_empty_when_ready():
    assert reset_portal_deploy_is_configured() is True
    assert missing_deploy_config() == []


def test_friendly_https_error_messages():
    assert "resolve" in _friendly_https_error(Exception("Failed to resolve 'reset.example.com'")).lower()
    assert "time" in _friendly_https_error(Exception("Read timed out. (read timeout=8)")).lower()


def test_teardown_reset_portal():
    portal = {
        "domain": "cleaver.click",
        "enabled": True,
        "portal_host": "reset.cleaver.click",
    }
    with patch("services.reset_portal_deploy.remove_reset_portal_cname", return_value={"outcome": "removed"}) as rm_cname, \
         patch("services.reset_portal_deploy.npm_delete_proxy_host", return_value=True) as rm_proxy, \
         patch("services.reset_portal_deploy.npm_delete_certificate", return_value=True) as rm_cert, \
         patch("services.reset_portal_deploy.cf_is_configured", return_value=True), \
         patch("services.reset_portal_deploy.npm_is_configured", return_value=True), \
         patch("services.reset_portal_deploy.audit"):
        result = teardown_reset_portal("cleaver.click", portal)

    rm_cname.assert_called_once_with("cleaver.click", "reset.cleaver.click", result["steps"])
    rm_proxy.assert_called_once_with("reset.cleaver.click", result["steps"])
    rm_cert.assert_called_once_with("reset.cleaver.click", result["steps"])


def test_deploy_reset_portal_orchestration():
    db.init_db()
    db.upsert_reset_portal("cleaver.click", True, "reset", "Cleaver")

    dns_result = {"host": "reset.cleaver.click", "target": "mxtools.t0m.sh", "outcome": "added", "steps": ["dns step"]}
    npm_result = {"certificate_mode": "letsencrypt_dns", "proxy_host_id": 2, "proxy_host_outcome": "created"}
    https_health = {"status": "pass", "message": "Portal is live"}

    with patch("services.reset_portal_deploy.deploy_reset_portal_cname", return_value=dns_result), \
         patch("services.reset_portal_deploy.deploy_reset_portal_proxy_letsencrypt", return_value=npm_result), \
         patch("services.reset_portal_deploy.cf_origin_ca_is_configured", return_value=False), \
         patch("services.reset_portal_deploy.audit"):
        result = deploy_reset_portal("cleaver.click", "reset")

    assert result["host"] == "reset.cleaver.click"
    assert result["npm"]["certificate_mode"] == "letsencrypt_dns"
    assert result["https"]["status"] == "pending"
    assert any("Let's Encrypt" in step for step in result["steps"])
