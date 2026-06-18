import requests
from flask import current_app

from models.db import get_env_config


def cf_origin_ca_is_configured():
    key = (get_env_config("CF_ORIGIN_CA_KEY") or "").strip()
    if not key:
        return False
    # ponytail: API tokens (cfut_) are not Origin CA keys; ignore to avoid auth failures.
    if key.startswith("cfut_"):
        return False
    return True


def create_origin_certificate(hostname):
    """Issue a Cloudflare Origin CA certificate for a single hostname."""
    service_key = (get_env_config("CF_ORIGIN_CA_KEY") or "").strip()
    if not service_key:
        raise ValueError("CF_ORIGIN_CA_KEY is not configured")

    hostname = hostname.lower().rstrip(".")
    response = requests.post(
        "https://api.cloudflare.com/client/v4/certificates",
        headers={
            "X-Auth-User-Service-Key": service_key,
            "Content-Type": "application/json",
        },
        json={
            "hostnames": [hostname],
            "requested_validity": 5475,
            "request_type": "origin-rsa",
        },
        timeout=30,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError(f"Cloudflare Origin CA request failed ({response.status_code})") from exc

    if not payload.get("success"):
        errors = payload.get("errors") or []
        message = errors[0].get("message", "Unknown Cloudflare Origin CA error") if errors else "Origin CA request failed"
        current_app.logger.error("Cloudflare Origin CA error: %s", payload)
        if "Authentication failed" in message:
            raise ValueError(
                "Cloudflare Origin CA authentication failed. "
                "CF_ORIGIN_CA_KEY must be the Origin CA key from "
                "SSL/TLS → Origin Server (not a regular API token)."
            )
        raise ValueError(message)

    result = payload.get("result") or {}
    certificate = result.get("certificate")
    private_key = result.get("private_key")
    if not certificate or not private_key:
        raise ValueError("Cloudflare Origin CA response missing certificate or private key")

    if not certificate.endswith("\n"):
        certificate += "\n"
    if not private_key.endswith("\n"):
        private_key += "\n"
    return certificate, private_key
