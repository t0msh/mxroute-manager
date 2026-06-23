from models.db import get_env_config
from services.cloudflare_api import cf_is_configured, cf_request
from services.reverse_proxy.base import BACKEND_CF_TUNNEL
from utils.validators import nested_dict_get, origin_http_url

_CATCH_ALL = {"service": "http_status:404"}


def _tunnel_id():
    return (get_env_config("CF_TUNNEL_ID") or "").strip()


def _tunnel_origin():
    return origin_http_url(get_env_config("CF_TUNNEL_ORIGIN") or "")


def cf_tunnel_cname_target():
    tunnel_id = _tunnel_id().lower()
    if not tunnel_id:
        return ""
    return f"{tunnel_id}.cfargotunnel.com"


def _ingress_list(config_payload):
    if not isinstance(config_payload, dict):
        return []
    config = nested_dict_get(config_payload, "result", "config")
    if not isinstance(config, dict):
        return []
    ingress = config.get("ingress")
    if not isinstance(ingress, list):
        return []
    return list(ingress)


def _fetch_ingress():
    tunnel_id = _tunnel_id()
    if not tunnel_id:
        raise ValueError("CF_TUNNEL_ID is not configured")
    account_id = (get_env_config("CF_ACCOUNT_ID") or "").strip()
    if not account_id:
        raise ValueError("CF_ACCOUNT_ID is not configured")
    payload = cf_request(
        "GET", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations"
    )
    return _ingress_list(payload)


def _put_ingress(ingress, steps=None):
    tunnel_id = _tunnel_id()
    account_id = (get_env_config("CF_ACCOUNT_ID") or "").strip()
    cf_request(
        "PUT",
        f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations",
        {"config": {"ingress": ingress}},
    )
    if steps is not None:
        steps.append(f"Updated Cloudflare Tunnel ingress ({len(ingress)} rules)")


def _normalize_ingress(ingress):
    rules = []
    catch_all = None
    for rule in ingress or []:
        if not isinstance(rule, dict):
            continue
        if rule.get("hostname"):
            rules.append(dict(rule))
        elif rule.get("service"):
            catch_all = dict(rule)
    if not catch_all:
        catch_all = dict(_CATCH_ALL)
    return rules, catch_all


def merge_tunnel_ingress_hostname(hostname, service, ingress=None):
    """Add or update a hostname rule; preserve other rules and catch-all."""
    hostname = hostname.lower().rstrip(".")
    if ingress is None:
        ingress = _fetch_ingress()
    rules, catch_all = _normalize_ingress(ingress)
    updated = []
    found = False
    for rule in rules:
        rule_host = (rule.get("hostname") or "").lower().rstrip(".")
        if rule_host == hostname:
            if rule.get("service") == service:
                updated.append(rule)
                found = True
            else:
                updated.append(
                    {
                        "hostname": hostname,
                        "service": service,
                        "originRequest": rule.get("originRequest") or {},
                    }
                )
                found = True
        else:
            updated.append(rule)
    if not found:
        updated.append(
            {
                "hostname": hostname,
                "service": service,
                "originRequest": {},
            }
        )
    updated.append(catch_all)
    return updated


def remove_tunnel_ingress_hostname(hostname, ingress=None):
    hostname = hostname.lower().rstrip(".")
    if ingress is None:
        ingress = _fetch_ingress()
    rules, catch_all = _normalize_ingress(ingress)
    kept = [
        rule
        for rule in rules
        if (rule.get("hostname") or "").lower().rstrip(".") != hostname
    ]
    kept.append(catch_all)
    return kept


class CfTunnelBackend:
    backend_id = BACKEND_CF_TUNNEL
    display_name = "Cloudflare Tunnel"

    def is_configured(self):
        return cf_is_configured() and bool(_tunnel_id()) and bool(_tunnel_origin())

    def missing_config(self):
        missing = []
        if not cf_is_configured():
            missing.append("Cloudflare (CF_API_TOKEN, CF_ACCOUNT_ID)")
        if not _tunnel_id():
            missing.append("CF_TUNNEL_ID")
        if not _tunnel_origin():
            missing.append("CF_TUNNEL_ORIGIN (e.g. 127.0.0.1:5000)")
        return missing

    def cname_target(self):
        return cf_tunnel_cname_target()

    def needs_cname_target_env(self):
        return False

    def supports_origin_ca(self):
        return False

    def provision_portal_host(self, portal_host, steps):
        portal_host = portal_host.lower().rstrip(".")
        service = _tunnel_origin()
        ingress = merge_tunnel_ingress_hostname(portal_host, service)
        existing = _fetch_ingress()
        rules, _ = _normalize_ingress(existing)
        outcome = "skipped"
        for rule in rules:
            if (rule.get("hostname") or "").lower().rstrip(".") == portal_host:
                if rule.get("service") == service:
                    outcome = "skipped"
                else:
                    outcome = "updated"
                break
        else:
            outcome = "created"

        if outcome == "skipped":
            steps.append(
                f"Cloudflare Tunnel ingress already configured for {portal_host}"
            )
        elif outcome == "updated":
            steps.append(
                f"Updating Cloudflare Tunnel ingress for {portal_host} → {service}"
            )
            _put_ingress(ingress, steps)
        else:
            steps.append(
                f"Adding Cloudflare Tunnel ingress for {portal_host} → {service}"
            )
            _put_ingress(ingress, steps)
        return {
            "certificate_mode": "cloudflare_edge",
            "proxy_host_outcome": outcome,
        }

    def delete_portal_host(self, portal_host, steps=None):
        portal_host = portal_host.lower().rstrip(".")
        ingress = remove_tunnel_ingress_hostname(portal_host)
        before = _fetch_ingress()
        rules_before, _ = _normalize_ingress(before)
        if not any(
            (r.get("hostname") or "").lower().rstrip(".") == portal_host
            for r in rules_before
        ):
            if steps is not None:
                steps.append(f"No Cloudflare Tunnel ingress found for {portal_host}.")
            return False
        _put_ingress(ingress, steps)
        if steps is not None:
            steps.append(f"Removed Cloudflare Tunnel ingress for {portal_host}")
        return True
