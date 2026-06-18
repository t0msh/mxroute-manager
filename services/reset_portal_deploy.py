import time

import requests

from models.db import build_portal_host
from services.cf_origin_ca import cf_origin_ca_is_configured, create_origin_certificate
from services.cloudflare import cf_is_configured, deploy_reset_portal_cname, check_reset_portal_dns, remove_reset_portal_cname
from services.mxroute import audit
from services.npm import (
    npm_is_configured,
    deploy_reset_portal_proxy,
    deploy_reset_portal_proxy_letsencrypt,
    npm_delete_proxy_host,
    npm_delete_certificate,
)


def reset_portal_deploy_is_configured():
    return cf_is_configured() and npm_is_configured()


def missing_deploy_config():
    missing = []
    if not cf_is_configured():
        missing.append("Cloudflare (CF_API_TOKEN, CF_ACCOUNT_ID)")
    if not npm_is_configured():
        missing.append("NPM_API_URL, NPM_IDENTITY, NPM_SECRET, NPM_FORWARD_HOST, NPM_FORWARD_PORT")
    from models.db import get_reset_portal_cname_target

    if not get_reset_portal_cname_target():
        missing.append("RESET_PORTAL_CNAME_TARGET")
    return missing


def check_reset_portal_https_quick(portal_host):
    """Single fast probe for UI status — avoid blocking requests."""
    return check_reset_portal_https(portal_host, timeout=8, retries=1, delay=0)


def _friendly_https_error(exc):
    text = str(exc).lower()
    if "failed to resolve" in text or "name or service not known" in text or "nameresolution" in text:
        return "Portal hostname does not resolve yet. Click Deploy Portal (DNS + NPM) if you have not already."
    if "timed out" in text or "timeout" in text:
        return "Portal did not respond in time. After deploy, certificate and DNS propagation can take a few minutes."
    if "connection refused" in text:
        return "Connection refused at origin. Check NPM proxy host and forwarding target."
    if "ssl" in text:
        return "SSL handshake failed. NPM certificate may still be issuing."
    return "Portal is not reachable yet."


def check_reset_portal_https(portal_host, timeout=10, retries=6, delay=5):
    portal_host = (portal_host or "").lower().rstrip(".")
    if not portal_host:
        return {"status": "disabled", "message": "Portal host is not configured."}

    url = f"https://{portal_host}/"
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


def _provision_npm_tls(portal_host, steps):
    if cf_origin_ca_is_configured():
        try:
            steps.append(f"Issuing Cloudflare Origin CA certificate for {portal_host}...")
            certificate_pem, private_key_pem = create_origin_certificate(portal_host)
            steps.append(f"Origin CA certificate issued for {portal_host}")
            steps.append("Configuring Nginx Proxy Manager proxy host...")
            return deploy_reset_portal_proxy(portal_host, certificate_pem, private_key_pem, steps)
        except ValueError as exc:
            steps.append(f"Origin CA skipped: {exc}")

    steps.append(
        f"Provisioning NPM Let's Encrypt certificate for {portal_host} (Cloudflare DNS challenge)..."
    )
    return deploy_reset_portal_proxy_letsencrypt(portal_host, steps)


def deploy_reset_portal(domain, prefix):
    missing = missing_deploy_config()
    if missing:
        raise ValueError("Reset portal deploy is not fully configured: " + ", ".join(missing))

    prefix = (prefix or "").strip().lower()
    if not prefix:
        raise ValueError("Subdomain prefix is required")

    domain = domain.lower().strip()
    portal_host = build_portal_host(prefix, domain)
    steps = []

    steps.append("Deploying Cloudflare CNAME...")
    dns_result = deploy_reset_portal_cname(domain, prefix)
    steps.extend(dns_result.get("steps") or [])

    npm_result = _provision_npm_tls(portal_host, steps)

    # ponytail: return quickly; LE issuance + HTTPS propagation happen async — status on refresh.
    https_health = {
        "status": "pending",
        "message": "DNS and NPM configured. HTTPS may take a few minutes to become available.",
    }

    audit(
        "reset_portal.deploy",
        target=domain,
        host=portal_host,
        dns=dns_result.get("outcome"),
        npm_proxy=npm_result.get("proxy_host_outcome"),
        cert_mode=npm_result.get("certificate_mode"),
        https=https_health.get("status"),
    )

    return {
        "host": portal_host,
        "dns": dns_result,
        "npm": npm_result,
        "https": https_health,
        "steps": steps,
    }


def teardown_reset_portal(domain, portal):
    """Best-effort removal of Cloudflare CNAME and NPM resources for a portal host."""
    host = (portal or {}).get("portal_host") or ""
    if not host:
        return {"steps": ["No portal host configured; nothing to remove."]}

    domain = domain.lower().strip()
    host = host.lower().rstrip(".")
    steps = []

    if cf_is_configured():
        try:
            remove_reset_portal_cname(domain, host, steps)
        except Exception as exc:
            steps.append(f"Cloudflare CNAME removal failed: {exc}")
    else:
        steps.append("Cloudflare not configured; skipped CNAME removal.")

    if npm_is_configured():
        try:
            npm_delete_proxy_host(host, steps)
            npm_delete_certificate(host, steps)
        except Exception as exc:
            steps.append(f"NPM cleanup failed: {exc}")
    else:
        steps.append("NPM not configured; skipped proxy host removal.")

    audit("reset_portal.teardown", target=domain, host=host)
    return {"host": host, "steps": steps}
