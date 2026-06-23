import time

import requests

from models.db import build_portal_host
from services.cloudflare import (
    cf_is_configured,
    deploy_reset_portal_cname,
    remove_reset_portal_cname,
)
from services.mxroute import audit
from services.reset_portal_mail import ensure_reset_sender_forwarder
from services.reverse_proxy import (
    get_backend,
    get_backend_id,
    portal_cname_target,
    proxy_is_configured,
    proxy_missing_config,
)
from utils.validators import public_https_origin


def reset_portal_deploy_is_configured():
    if not cf_is_configured() or not proxy_is_configured():
        return False
    backend = get_backend()
    if backend.needs_cname_target_env() and not portal_cname_target():
        return False
    return True


def missing_deploy_config():
    missing = []
    if not cf_is_configured():
        missing.append("Cloudflare (CF_API_TOKEN, CF_ACCOUNT_ID)")
    missing.extend(proxy_missing_config())
    backend = get_backend()
    if backend.needs_cname_target_env() and not portal_cname_target():
        missing.append("RESET_PORTAL_CNAME_TARGET")
    return missing


def check_reset_portal_https_quick(portal_host):
    """Single fast probe for UI status — avoid blocking requests."""
    return check_reset_portal_https(portal_host, timeout=8, retries=1, delay=0)


def _friendly_https_error(exc):
    text = str(exc).lower()
    if (
        "failed to resolve" in text
        or "name or service not known" in text
        or "nameresolution" in text
    ):
        return "Portal hostname does not resolve yet. Click Deploy Portal if you have not already."
    if "timed out" in text or "timeout" in text:
        return "Portal did not respond in time. After deploy, certificate and DNS propagation can take a few minutes."
    if "connection refused" in text:
        backend_id = get_backend_id()
        if backend_id == "cloudflare_tunnel":
            return (
                "Connection refused at origin. Check tunnel ingress and that cloudflared is running."
            )
        return (
            "Connection refused at origin. Check reverse proxy host and forwarding target."
        )
    if "ssl" in text:
        return "SSL handshake failed. Certificate may still be issuing."
    return "Portal is not reachable yet."


def check_reset_portal_https(portal_host, timeout=10, retries=6, delay=5):
    portal_host = (portal_host or "").lower().rstrip(".")
    if not portal_host:
        return {"status": "disabled", "message": "Portal host is not configured."}

    url = f"{public_https_origin(portal_host)}/"
    last_result = None
    for attempt in range(retries):
        last_result = _check_reset_portal_https_once(portal_host, url, timeout)
        if last_result.get("status") == "pass":
            return last_result
        if attempt < retries - 1:
            time.sleep(delay)
    return last_result


def _check_reset_portal_https_once(portal_host, url, timeout):
    try:
        response = requests.get(url, timeout=timeout, allow_redirects=True)
    except requests.exceptions.SSLError:
        return {
            "status": "fail",
            "message": f"SSL error reaching {url} (Cloudflare 525 or origin cert issue).",
            "url": url,
        }
    except requests.exceptions.RequestException as exc:
        return {
            "status": "pending",
            "message": _friendly_https_error(exc),
            "url": url,
        }

    if response.status_code == 525:
        return {
            "status": "fail",
            "message": "Cloudflare 525: origin SSL handshake failed.",
            "url": url,
            "http_status": 525,
        }

    if response.status_code == 200 and "Reset Mailbox Password" in response.text:
        return {
            "status": "pass",
            "message": f"Portal is live at {url}",
            "url": url,
            "http_status": response.status_code,
        }

    return {
        "status": "warn",
        "message": f"HTTPS reachable ({response.status_code}) but portal page was not detected.",
        "url": url,
        "http_status": response.status_code,
    }


def deploy_reset_portal(domain, prefix, admin_email=None):
    missing = missing_deploy_config()
    if missing:
        raise ValueError(
            "Reset portal deploy is not fully configured: " + ", ".join(missing)
        )

    prefix = (prefix or "").strip().lower()
    if not prefix:
        raise ValueError("Subdomain prefix is required")

    domain = domain.lower().strip()
    portal_host = build_portal_host(prefix, domain)
    steps = []
    backend = get_backend()

    admin_email = (admin_email or "").strip().lower()
    if not admin_email:
        raise ValueError(
            "A contact email is required before deploying a reset portal. "
            "Add one in Settings or Access Control (or sign in with an email-based login)."
        )

    steps.append("Ensuring reset@ sender forwarder on MXroute...")
    ensure_reset_sender_forwarder(domain, admin_email, steps)

    steps.append("Deploying Cloudflare CNAME...")
    dns_result = deploy_reset_portal_cname(domain, prefix)
    steps.extend(dns_result.get("steps") or [])

    steps.append(f"Configuring {backend.display_name}...")
    proxy_result = backend.provision_portal_host(portal_host, steps)

    # ponytail: return quickly; LE issuance + HTTPS propagation happen async — status on refresh.
    https_health = {
        "status": "pending",
        "message": (
            "DNS and reverse proxy configured. HTTPS may take a few minutes to become available."
        ),
    }

    audit(
        "reset_portal.deploy",
        target=domain,
        host=portal_host,
        dns=dns_result.get("outcome"),
        proxy_backend=backend.backend_id,
        proxy_host=proxy_result.get("proxy_host_outcome"),
        cert_mode=proxy_result.get("certificate_mode"),
        https=https_health.get("status"),
    )

    return {
        "host": portal_host,
        "dns": dns_result,
        "proxy": proxy_result,
        "proxy_backend": backend.backend_id,
        "https": https_health,
        "steps": steps,
    }


def teardown_reset_portal(domain, portal):
    """Best-effort removal of Cloudflare CNAME and reverse-proxy resources for a portal host."""
    host = (portal or {}).get("portal_host") or ""
    if not host:
        return {"steps": ["No portal host configured; nothing to remove."]}

    domain = domain.lower().strip()
    host = host.lower().rstrip(".")
    steps = []
    backend = get_backend()

    if cf_is_configured():
        try:
            remove_reset_portal_cname(domain, host, steps)
        except Exception as exc:
            steps.append(f"Cloudflare CNAME removal failed: {exc}")
    else:
        steps.append("Cloudflare not configured; skipped CNAME removal.")

    if proxy_is_configured():
        try:
            backend.delete_portal_host(host, steps)
        except Exception as exc:
            steps.append(f"{backend.display_name} cleanup failed: {exc}")
    else:
        steps.append("Reverse proxy not configured; skipped proxy host removal.")

    audit("reset_portal.teardown", target=domain, host=host)
    return {"host": host, "steps": steps}
