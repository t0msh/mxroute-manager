"""Tests for reverse-proxy backend abstraction."""

from unittest.mock import patch

from services.reverse_proxy.base import get_backend_id
from services.reverse_proxy.cf_tunnel import (
    CfTunnelBackend,
    merge_tunnel_ingress_hostname,
    remove_tunnel_ingress_hostname,
)
from services.reverse_proxy.manual import ManualBackend, manual_snippets
from services.reverse_proxy.traefik import (
    upsert_traefik_portal_fragment,
    delete_traefik_portal_fragment,
)


def test_merge_tunnel_ingress_adds_hostname():
    ingress = [{"hostname": "app.example.com", "service": "http://localhost:80"}]
    merged = merge_tunnel_ingress_hostname(
        "reset.example.com", "http://127.0.0.1:5000", ingress
    )
    assert merged[0]["hostname"] == "app.example.com"
    assert merged[1]["hostname"] == "reset.example.com"
    assert merged[1]["service"] == "http://127.0.0.1:5000"
    assert merged[-1]["service"] == "http_status:404"


def test_merge_tunnel_ingress_updates_existing():
    ingress = [
        {"hostname": "reset.example.com", "service": "http://old:5000"},
        {"service": "http_status:404"},
    ]
    merged = merge_tunnel_ingress_hostname(
        "reset.example.com", "http://127.0.0.1:5000", ingress
    )
    assert len(merged) == 2
    assert merged[0]["service"] == "http://127.0.0.1:5000"


def test_remove_tunnel_ingress_hostname():
    ingress = [
        {"hostname": "reset.example.com", "service": "http://127.0.0.1:5000"},
        {"hostname": "app.example.com", "service": "http://localhost:80"},
        {"service": "http_status:404"},
    ]
    merged = remove_tunnel_ingress_hostname("reset.example.com", ingress)
    assert len(merged) == 2
    assert merged[0]["hostname"] == "app.example.com"
    assert merged[-1]["service"] == "http_status:404"


def test_cf_tunnel_backend_provision(monkeypatch):
    monkeypatch.setenv("CF_TUNNEL_ID", "abc-123")
    monkeypatch.setenv("CF_TUNNEL_ORIGIN", "http://127.0.0.1:5000")
    backend = CfTunnelBackend()
    steps = []
    with (
        patch(
            "services.reverse_proxy.cf_tunnel._fetch_ingress",
            return_value=[{"service": "http_status:404"}],
        ),
        patch("services.reverse_proxy.cf_tunnel._put_ingress") as put_ingress,
        patch("services.reverse_proxy.cf_tunnel.cf_is_configured", return_value=True),
    ):
        result = backend.provision_portal_host("reset.example.com", steps)
    put_ingress.assert_called_once()
    assert result["certificate_mode"] == "cloudflare_edge"
    assert result["proxy_host_outcome"] == "created"


def test_manual_backend_not_configured():
    backend = ManualBackend()
    assert backend.is_configured() is False
    assert backend.missing_config()


def test_manual_snippets_include_host():
    snippets = manual_snippets("reset.example.com")
    assert "reset.example.com" in snippets["nginx"]
    assert "reset.example.com" in snippets["caddy"]


def test_traefik_fragment_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAEFIK_DYNAMIC_DIR", str(tmp_path))
    monkeypatch.setenv("TRAEFIK_ORIGIN_URL", "http://127.0.0.1:5000")
    outcome = upsert_traefik_portal_fragment("reset.example.com", steps=[])
    assert outcome == "created"
    outcome2 = upsert_traefik_portal_fragment("reset.example.com", steps=[])
    assert outcome2 == "skipped"
    assert delete_traefik_portal_fragment("reset.example.com", steps=[]) is True
    assert delete_traefik_portal_fragment("reset.example.com", steps=[]) is False


def test_get_backend_id_defaults_to_npm(monkeypatch):
    monkeypatch.delenv("REVERSE_PROXY_BACKEND", raising=False)
    assert get_backend_id() == "npm"


def test_get_backend_id_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("REVERSE_PROXY_BACKEND", "not-a-proxy")
    assert get_backend_id() == "npm"
