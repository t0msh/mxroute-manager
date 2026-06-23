import requests
from flask import current_app

from models.db import get_config_value, get_env_config
from services.reverse_proxy.base import BACKEND_CADDY
from utils.validators import nested_dict_get

_SERVER_NAME = "mxroute_manager_portals"


def _admin_base():
    return (get_env_config("CADDY_ADMIN_URL") or "").strip().rstrip("/")


def _admin_headers():
    headers = {"Content-Type": "application/json"}
    token = (get_env_config("CADDY_ADMIN_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _origin_dial():
    origin = (get_env_config("CADDY_ORIGIN") or "").strip()
    if not origin:
        return ""
    if "://" in origin:
        return origin.split("://", 1)[1]
    return origin


def caddy_is_configured():
    return bool(_admin_base() and _origin_dial())


def _caddy_request(method, path, json_payload=None):
    if not caddy_is_configured():
        raise ValueError("Caddy is not configured")
    url = f"{_admin_base()}{path}"
    response = requests.request(
        method,
        url,
        json=json_payload,
        headers=_admin_headers(),
        timeout=60,
    )
    if response.status_code >= 400:
        body = response.text[:300]
        current_app.logger.error("Caddy admin error %s %s: %s", method, path, body)
        raise ValueError(body or f"Caddy request failed ({response.status_code})")
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def _load_config():
    try:
        return _caddy_request("GET", "/config/")
    except ValueError:
        return {}


def _host_route(hostname, dial):
    return {
        "match": [{"host": [hostname]}],
        "handle": [
            {
                "handler": "reverse_proxy",
                "upstreams": [{"dial": dial}],
            }
        ],
        "terminal": True,
    }


def _ensure_server(config):
    config = config or {}
    apps = config.setdefault("apps", {})
    http = apps.setdefault("http", {})
    servers = http.setdefault("servers", {})
    server = servers.setdefault(
        _SERVER_NAME,
        {"listen": [":443"], "routes": []},
    )
    if ":443" not in server.get("listen", []):
        server.setdefault("listen", []).append(":443")
    server.setdefault("routes", [])
    return config


def _tls_policy_for_host(hostname):
    cf_token = get_config_value("CF_API_TOKEN")
    if not cf_token:
        raise ValueError("CF_API_TOKEN is required for Caddy DNS ACME")
    return {
        "subjects": [hostname],
        "issuers": [
            {
                "module": "acme",
                "challenges": {
                    "dns": {
                        "provider": {
                            "name": "cloudflare",
                            "api_token": cf_token,
                        }
                    }
                },
            }
        ],
    }


def _upsert_tls_policy(config, hostname):
    apps = config.setdefault("apps", {})
    tls = apps.setdefault("tls", {})
    automation = tls.setdefault("automation", {})
    policies = automation.setdefault("policies", [])
    for policy in policies:
        subjects = [s.lower() for s in policy.get("subjects") or []]
        if hostname in subjects:
            return
    policies.append(_tls_policy_for_host(hostname))


def _caddy_portal_server(config):
    servers = nested_dict_get(config, "apps", "http", "servers")
    if not isinstance(servers, dict):
        return None
    return servers.get(_SERVER_NAME)


def _route_hosts(route):
    hosts = []
    for match in route.get("match") or []:
        if isinstance(match, dict):
            hosts.extend(match.get("host") or [])
    return hosts


def upsert_caddy_portal_route(hostname, steps=None):
    hostname = hostname.lower().rstrip(".")
    dial = _origin_dial()
    config = _ensure_server(_load_config())
    server = config["apps"]["http"]["servers"][_SERVER_NAME]
    routes = server.get("routes") or []
    new_routes = []
    outcome = "created"
    for route in routes:
        if hostname in [h.lower() for h in _route_hosts(route)]:
            outcome = "updated"
            new_routes.append(_host_route(hostname, dial))
        else:
            new_routes.append(route)
    if outcome == "created":
        new_routes.append(_host_route(hostname, dial))
    server["routes"] = new_routes
    _upsert_tls_policy(config, hostname)
    _caddy_request("POST", "/load", json_payload=config)
    if steps is not None:
        steps.append(
            f"{'Updated' if outcome == 'updated' else 'Created'} Caddy route for "
            f"{hostname} → {dial}"
        )
    return outcome


class CaddyBackend:
    backend_id = BACKEND_CADDY
    display_name = "Caddy"

    def is_configured(self):
        return caddy_is_configured()

    def missing_config(self):
        missing = []
        if not _admin_base():
            missing.append("CADDY_ADMIN_URL")
        if not _origin_dial():
            missing.append("CADDY_ORIGIN (host:port, e.g. 127.0.0.1:5000)")
        return missing

    def cname_target(self):
        return None

    def needs_cname_target_env(self):
        return True

    def supports_origin_ca(self):
        return False

    def provision_portal_host(self, portal_host, steps):
        outcome = upsert_caddy_portal_route(portal_host, steps)
        return {
            "certificate_mode": "caddy_acme_dns",
            "proxy_host_outcome": outcome,
        }

    def delete_portal_host(self, portal_host, steps=None):
        hostname = (portal_host or "").lower().rstrip(".")
        config = _load_config()
        server = _caddy_portal_server(config)
        if not server:
            if steps is not None:
                steps.append(f"No Caddy server {_SERVER_NAME} found.")
            return False
        routes = server.get("routes") or []
        kept = []
        removed = False
        for route in routes:
            if hostname in [h.lower() for h in _route_hosts(route)]:
                removed = True
            else:
                kept.append(route)
        if not removed:
            if steps is not None:
                steps.append(f"No Caddy route found for {hostname}.")
            return False
        server["routes"] = kept
        _caddy_request("POST", "/load", json_payload=config)
        if steps is not None:
            steps.append(f"Removed Caddy route for {hostname}")
        return True
