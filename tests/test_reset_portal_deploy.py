"""Tests for reset portal deploy orchestration."""

from unittest.mock import MagicMock, patch

from services.reverse_proxy.npm_backend import NpmBackend
from services.reset_portal_deploy import (
    missing_deploy_config,
    reset_portal_deploy_is_configured,
    deploy_reset_portal,
    teardown_reset_portal,
    _friendly_https_error,
)


def test_npm_backend_is_configured():
    backend = NpmBackend()
    assert backend.is_configured() is True


def test_missing_deploy_config_empty_when_ready():
    assert reset_portal_deploy_is_configured() is True
    assert missing_deploy_config() == []


def test_deploy_reset_portal_requires_contact_email(fresh_db):
    fresh_db.upsert_reset_portal("cleaver.click", True, "reset", "Cleaver")

    try:
        deploy_reset_portal("cleaver.click", "reset", admin_email="")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "contact email is required" in str(exc).lower()


def test_friendly_https_error_messages():
    assert (
        "resolve"
        in _friendly_https_error(
            Exception("Failed to resolve 'reset.example.com'")
        ).lower()
    )
    assert (
        "time"
        in _friendly_https_error(Exception("Read timed out. (read timeout=8)")).lower()
    )


def test_friendly_https_error_tunnel_mode(monkeypatch):
    monkeypatch.setenv("REVERSE_PROXY_BACKEND", "cloudflare_tunnel")
    msg = _friendly_https_error(Exception("Connection refused"))
    assert "cloudflared" in msg.lower()


def test_teardown_reset_portal():
    portal = {
        "domain": "cleaver.click",
        "enabled": True,
        "portal_host": "reset.cleaver.click",
    }
    mock_backend = MagicMock()
    mock_backend.display_name = "Nginx Proxy Manager"
    mock_backend.delete_portal_host.return_value = True

    with (
        patch(
            "services.reset_portal_deploy.remove_reset_portal_cname",
            return_value={"outcome": "removed"},
        ) as rm_cname,
        patch("services.reset_portal_deploy.get_backend", return_value=mock_backend),
        patch("services.reset_portal_deploy.cf_is_configured", return_value=True),
        patch("services.reset_portal_deploy.proxy_is_configured", return_value=True),
        patch("services.reset_portal_deploy.audit"),
    ):
        result = teardown_reset_portal("cleaver.click", portal)

    rm_cname.assert_called_once_with(
        "cleaver.click", "reset.cleaver.click", result["steps"]
    )
    mock_backend.delete_portal_host.assert_called_once_with(
        "reset.cleaver.click", result["steps"]
    )


def test_deploy_reset_portal_orchestration(fresh_db):
    fresh_db.upsert_reset_portal("cleaver.click", True, "reset", "Cleaver")

    dns_result = {
        "host": "reset.cleaver.click",
        "target": "mxtools.t0m.sh",
        "outcome": "added",
        "steps": ["dns step"],
    }
    proxy_result = {
        "certificate_mode": "letsencrypt_dns",
        "proxy_host_outcome": "created",
    }
    mock_backend = MagicMock()
    mock_backend.display_name = "Nginx Proxy Manager"
    mock_backend.backend_id = "npm"
    mock_backend.provision_portal_host.return_value = proxy_result

    with (
        patch(
            "services.reset_portal_deploy.deploy_reset_portal_cname",
            return_value=dns_result,
        ),
        patch(
            "services.reset_portal_deploy.get_backend",
            return_value=mock_backend,
        ),
        patch(
            "services.reset_portal_deploy.ensure_reset_sender_forwarder",
            return_value="added",
        ) as mock_forwarder,
        patch("services.reset_portal_deploy.audit"),
    ):
        result = deploy_reset_portal(
            "cleaver.click", "reset", admin_email="admin@example.com"
        )

    mock_forwarder.assert_called_once_with(
        "cleaver.click", "admin@example.com", result["steps"]
    )
    assert result["host"] == "reset.cleaver.click"
    assert result["proxy"]["certificate_mode"] == "letsencrypt_dns"
    assert result["https"]["status"] == "pending"
    mock_backend.provision_portal_host.assert_called_once()
