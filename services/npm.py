import time

import requests
from flask import current_app

from models.db import get_env_config

# ponytail: single-process NPM token cache; expires per API response.
_cached_npm_token = None
_cached_npm_token_expires = 0


def npm_api_base():
    base = (get_env_config("NPM_API_URL") or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/api"


def npm_is_configured():
    return bool(
        npm_api_base()
        and (get_env_config("NPM_IDENTITY") or "").strip()
        and (get_env_config("NPM_SECRET") or "").strip()
        and (get_env_config("NPM_FORWARD_HOST") or "").strip()
        and (get_env_config("NPM_FORWARD_PORT") or "").strip()
    )


def npm_tls_verify():
    return (get_env_config("NPM_TLS_VERIFY", "true") or "true").lower() in ("true", "1", "yes")


def npm_forward_target():
    host = (get_env_config("NPM_FORWARD_HOST") or "").strip()
    port_raw = (get_env_config("NPM_FORWARD_PORT") or "5000").strip()
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError("NPM_FORWARD_PORT must be an integer") from exc
    if not host:
        raise ValueError("NPM_FORWARD_HOST is not configured")
    return host, port


def _fetch_npm_token():
    global _cached_npm_token, _cached_npm_token_expires
    now = time.time()
    if _cached_npm_token and now < _cached_npm_token_expires - 60:
        return _cached_npm_token

    identity = (get_env_config("NPM_IDENTITY") or "").strip()
    secret = get_env_config("NPM_SECRET") or ""
    if not identity or not secret:
        raise ValueError("NPM credentials are not configured")

    url = f"{npm_api_base()}/tokens"
    response = requests.post(
        url,
        json={"identity": identity, "secret": secret},
        timeout=30,
        verify=npm_tls_verify(),
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("token")
    if not token:
        raise ValueError("NPM authentication failed: no token returned")

    expires_raw = payload.get("expires")
    expires_at = now + 3600
    if isinstance(expires_raw, str):
        try:
            from datetime import datetime

            expires_at = datetime.fromisoformat(expires_raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass

    _cached_npm_token = token
    _cached_npm_token_expires = expires_at
    return token


def npm_request(method, path, json_payload=None, files=None):
    if not npm_is_configured():
        raise ValueError("Nginx Proxy Manager is not configured")

    url = f"{npm_api_base()}{path}"
    headers = {
        "Authorization": f"Bearer {_fetch_npm_token()}",
        "Accept": "application/json",
    }
    if json_payload is not None:
        headers["Content-Type"] = "application/json"

    response = requests.request(
        method,
        url,
        json=json_payload,
        files=files,
        headers=headers,
        timeout=60,
        verify=npm_tls_verify(),
    )
    if response.status_code >= 400:
        body = response.text[:300]
        current_app.logger.error("NPM HTTP error %s %s: %s", method, path, body)
        try:
            payload = response.json()
            message = payload.get("error", {}).get("message") or payload.get("message") or body
        except ValueError:
            message = body or f"NPM request failed ({response.status_code})"
        raise ValueError(message)

    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def npm_list_proxy_hosts():
    return npm_request("GET", "/nginx/proxy-hosts")


def npm_find_proxy_host(hostname):
    hostname = hostname.lower().rstrip(".")
    for host in npm_list_proxy_hosts():
        names = [name.lower().rstrip(".") for name in host.get("domain_names") or []]
        if hostname in names:
            return host
    return None


def npm_list_certificates():
    return npm_request("GET", "/nginx/certificates")


def npm_find_certificate(hostname):
    hostname = hostname.lower().rstrip(".")
    for cert in npm_list_certificates():
        names = [name.lower().rstrip(".") for name in cert.get("domain_names") or []]
        if hostname in names:
            return cert
    return None


def npm_upsert_custom_certificate(hostname, certificate_pem, private_key_pem, steps):
    hostname = hostname.lower().rstrip(".")
    existing = npm_find_certificate(hostname)
    if existing:
        cert_id = existing["id"]
        if steps is not None:
            steps.append(f"Updating NPM certificate for {hostname}")
        npm_request(
            "POST",
            f"/nginx/certificates/{cert_id}/upload",
            files={
                "certificate": (f"{hostname}.crt", certificate_pem, "application/x-pem-file"),
                "certificate_key": (f"{hostname}.key", private_key_pem, "application/x-pem-file"),
            },
        )
        return cert_id, "updated"

    if steps is not None:
        steps.append(f"Creating NPM certificate for {hostname}")
    created = npm_request(
        "POST",
        "/nginx/certificates",
        json_payload={
            "provider": "other",
            "nice_name": f"{hostname} (mxroute-manager)",
            "domain_names": [hostname],
        },
    )
    cert_id = created.get("id")
    if not cert_id:
        raise ValueError("NPM certificate creation failed: missing id")

    npm_request(
        "POST",
        f"/nginx/certificates/{cert_id}/upload",
        files={
            "certificate": (f"{hostname}.crt", certificate_pem, "application/x-pem-file"),
            "certificate_key": (f"{hostname}.key", private_key_pem, "application/x-pem-file"),
        },
    )
    return cert_id, "created"


def _proxy_host_payload(hostname, certificate_id, forward_host, forward_port):
    return {
        "domain_names": [hostname],
        "forward_scheme": "http",
        "forward_host": forward_host,
        "forward_port": forward_port,
        "certificate_id": certificate_id,
        "access_list_id": 0,
        "ssl_forced": True,
        "block_exploits": True,
        "caching_enabled": False,
        "allow_websocket_upgrade": False,
        "http2_support": True,
        "enabled": True,
        "meta": {"letsencrypt_agree": False, "dns_challenge": False},
        "advanced_config": "",
        "locations": [],
    }


def npm_enable_proxy_host(host_id):
    try:
        npm_request("POST", f"/nginx/proxy-hosts/{host_id}/enable")
    except ValueError as exc:
        if "already enabled" not in str(exc).lower():
            raise


def npm_upsert_proxy_host(hostname, certificate_id, steps):
    hostname = hostname.lower().rstrip(".")
    forward_host, forward_port = npm_forward_target()
    existing = npm_find_proxy_host(hostname)

    if existing:
        host_id = existing["id"]
        payload = _proxy_host_payload(hostname, certificate_id, forward_host, forward_port)
        if steps is not None:
            steps.append(f"Updating NPM proxy host for {hostname} → {forward_host}:{forward_port}")
        npm_request("PUT", f"/nginx/proxy-hosts/{host_id}", json_payload=payload)
        npm_enable_proxy_host(host_id)
        return host_id, "updated"

    if steps is not None:
        steps.append(f"Creating NPM proxy host for {hostname} → {forward_host}:{forward_port}")
    created = npm_request(
        "POST",
        "/nginx/proxy-hosts",
        json_payload=_proxy_host_payload(hostname, certificate_id, forward_host, forward_port),
    )
    host_id = created.get("id")
    if not host_id:
        raise ValueError("NPM proxy host creation failed: missing id")
    npm_enable_proxy_host(host_id)
    return host_id, "created"


def deploy_reset_portal_proxy(hostname, certificate_pem, private_key_pem, steps):
    cert_id, cert_outcome = npm_upsert_custom_certificate(
        hostname, certificate_pem, private_key_pem, steps
    )
    host_id, host_outcome = npm_upsert_proxy_host(hostname, cert_id, steps)
    return {
        "certificate_id": cert_id,
        "certificate_outcome": cert_outcome,
        "certificate_mode": "origin_ca",
        "proxy_host_id": host_id,
        "proxy_host_outcome": host_outcome,
    }


def _letsencrypt_email():
    email = (get_env_config("NPM_LETSENCRYPT_EMAIL") or get_env_config("NPM_IDENTITY") or "").strip()
    if not email:
        raise ValueError("NPM_IDENTITY or NPM_LETSENCRYPT_EMAIL is required for Let's Encrypt")
    return email


def _proxy_host_payload_letsencrypt(hostname, forward_host, forward_port):
    from models.db import get_config_value

    cf_token = get_config_value("CF_API_TOKEN")
    if not cf_token:
        raise ValueError("CF_API_TOKEN is required for Let's Encrypt DNS challenge")

    return {
        "domain_names": [hostname],
        "forward_scheme": "http",
        "forward_host": forward_host,
        "forward_port": forward_port,
        "certificate_id": "new",
        "access_list_id": 0,
        "ssl_forced": True,
        "block_exploits": True,
        "caching_enabled": False,
        "allow_websocket_upgrade": False,
        "http2_support": True,
        "enabled": True,
        "meta": {
            "letsencrypt_agree": True,
            "letsencrypt_email": _letsencrypt_email(),
            "dns_challenge": True,
            "dns_provider": "cloudflare",
            "dns_provider_credentials": f"dns_cloudflare_api_token = {cf_token}",
            "propagation_seconds": 30,
        },
        "advanced_config": "",
        "locations": [],
    }


def deploy_reset_portal_proxy_letsencrypt(hostname, steps):
    """Create/update NPM proxy host; NPM provisions LE cert via Cloudflare DNS-01."""
    hostname = hostname.lower().rstrip(".")
    forward_host, forward_port = npm_forward_target()
    payload = _proxy_host_payload_letsencrypt(hostname, forward_host, forward_port)
    existing = npm_find_proxy_host(hostname)

    if existing:
        host_id = existing["id"]
        if steps is not None:
            steps.append(
                f"Updating NPM proxy host for {hostname} with Let's Encrypt (Cloudflare DNS)..."
            )
        npm_request("PUT", f"/nginx/proxy-hosts/{host_id}", json_payload=payload)
        npm_enable_proxy_host(host_id)
        return {
            "certificate_mode": "letsencrypt_dns",
            "proxy_host_id": host_id,
            "proxy_host_outcome": "updated",
        }

    if steps is not None:
        steps.append(
            f"Creating NPM proxy host for {hostname} with Let's Encrypt (Cloudflare DNS)..."
        )
    created = npm_request("POST", "/nginx/proxy-hosts", json_payload=payload)
    host_id = created.get("id")
    if not host_id:
        raise ValueError("NPM proxy host creation failed: missing id")
    npm_enable_proxy_host(host_id)
    return {
        "certificate_mode": "letsencrypt_dns",
        "proxy_host_id": host_id,
        "proxy_host_outcome": "created",
    }


def npm_wait_for_certificate(hostname, timeout=90, interval=5, steps=None):
    """Poll NPM until LE/custom cert exists for hostname (provisioning is async)."""
    import time

    hostname = hostname.lower().rstrip(".")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if npm_find_certificate(hostname):
            if steps is not None:
                steps.append(f"NPM certificate ready for {hostname}")
            return True
        time.sleep(interval)
    if steps is not None:
        steps.append(
            f"NPM certificate for {hostname} still provisioning; HTTPS may take a few more minutes."
        )
    return False


def npm_delete_proxy_host(hostname, steps=None):
    hostname = hostname.lower().rstrip(".")
    existing = npm_find_proxy_host(hostname)
    if not existing:
        if steps is not None:
            steps.append(f"No NPM proxy host found for {hostname}.")
        return False
    npm_request("DELETE", f"/nginx/proxy-hosts/{existing['id']}")
    if steps is not None:
        steps.append(f"Removed NPM proxy host for {hostname}")
    return True


def npm_delete_certificate(hostname, steps=None):
    hostname = hostname.lower().rstrip(".")
    existing = npm_find_certificate(hostname)
    if not existing:
        if steps is not None:
            steps.append(f"No NPM certificate found for {hostname}.")
        return False
    npm_request("DELETE", f"/nginx/certificates/{existing['id']}")
    if steps is not None:
        steps.append(f"Removed NPM certificate for {hostname}")
    return True
