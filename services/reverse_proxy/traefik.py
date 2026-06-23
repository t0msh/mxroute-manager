import os
import re

from models.db import get_env_config
from services.reverse_proxy.base import BACKEND_TRAEFIK

_SAFE_NAME = re.compile(r"[^a-z0-9.-]+")


def _dynamic_dir():
    return (get_env_config("TRAEFIK_DYNAMIC_DIR") or "").strip()


def _origin_url():
    origin = (get_env_config("TRAEFIK_ORIGIN_URL") or "").strip()
    if not origin:
        return ""
    if "://" not in origin:
        origin = f"http://{origin}"
    return origin.rstrip("/")


def _cert_resolver():
    return (get_env_config("TRAEFIK_CERT_RESOLVER") or "cloudflare").strip()


def traefik_is_configured():
    return bool(_dynamic_dir() and _origin_url())


def _fragment_name(hostname):
    safe = _SAFE_NAME.sub("-", hostname.lower().rstrip("."))
    return f"mxroute-portal-{safe}"


def _yaml_fragment(hostname):
    name = _fragment_name(hostname)
    resolver = _cert_resolver()
    origin = _origin_url()
    return f"""# Managed by mxroute-manager — do not edit by hand
http:
  routers:
    {name}:
      rule: Host(`{hostname}`)
      entryPoints:
        - websecure
      service: {name}
      tls:
        certResolver: {resolver}
  services:
    {name}:
      loadBalancer:
        servers:
          - url: "{origin}/"
"""


def _fragment_path(hostname):
    return os.path.join(_dynamic_dir(), f"{_fragment_name(hostname)}.yml")


def upsert_traefik_portal_fragment(hostname, steps=None):
    hostname = hostname.lower().rstrip(".")
    dynamic_dir = _dynamic_dir()
    os.makedirs(dynamic_dir, exist_ok=True)
    path = _fragment_path(hostname)
    content = _yaml_fragment(hostname)
    outcome = "created"
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            if handle.read() == content:
                if steps is not None:
                    steps.append(f"Traefik dynamic config already present for {hostname}")
                return "skipped"
        outcome = "updated"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    if steps is not None:
        steps.append(
            f"{'Updated' if outcome == 'updated' else 'Created'} Traefik config "
            f"{os.path.basename(path)}"
        )
    return outcome


def delete_traefik_portal_fragment(hostname, steps=None):
    path = _fragment_path(hostname)
    if not os.path.isfile(path):
        if steps is not None:
            steps.append(f"No Traefik dynamic config found for {hostname}.")
        return False
    os.remove(path)
    if steps is not None:
        steps.append(f"Removed Traefik config {os.path.basename(path)}")
    return True


class TraefikBackend:
    backend_id = BACKEND_TRAEFIK
    display_name = "Traefik"

    def is_configured(self):
        return traefik_is_configured()

    def missing_config(self):
        missing = []
        if not _dynamic_dir():
            missing.append("TRAEFIK_DYNAMIC_DIR")
        if not _origin_url():
            missing.append("TRAEFIK_ORIGIN_URL (e.g. http://127.0.0.1:5000)")
        return missing

    def cname_target(self):
        return None

    def needs_cname_target_env(self):
        return True

    def supports_origin_ca(self):
        return False

    def provision_portal_host(self, portal_host, steps):
        outcome = upsert_traefik_portal_fragment(portal_host, steps)
        return {
            "certificate_mode": "traefik_cert_resolver",
            "proxy_host_outcome": outcome,
        }

    def delete_portal_host(self, portal_host, steps=None):
        return delete_traefik_portal_fragment(portal_host, steps)
