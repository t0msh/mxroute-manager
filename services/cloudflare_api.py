import requests
from flask import current_app

from models.db import get_config_value


def cf_is_configured():
    return bool(get_config_value("CF_API_TOKEN") and get_config_value("CF_ACCOUNT_ID"))


def cf_request(method, path, payload=None):
    cf_token = get_config_value("CF_API_TOKEN")
    if not cf_token:
        raise ValueError("Cloudflare API token not configured")

    url = f"https://api.cloudflare.com/client/v4{path}"
    headers = {
        "Authorization": f"Bearer {cf_token}",
        "Content-Type": "application/json",
    }

    if method not in ("GET", "POST", "PUT", "DELETE"):
        raise ValueError("Unsupported Cloudflare method")

    response = None
    try:
        response = requests.request(
            method, url, json=payload, headers=headers, timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        status = response.status_code if response is not None else "unknown"
        body = response.text[:200] if response is not None else ""
        current_app.logger.error(f"Cloudflare HTTP error {status}: {body}")
        try:
            return response.json()
        except (ValueError, AttributeError):
            raise ValueError(f"Cloudflare request failed ({status}): {body}") from e
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Cloudflare request failed: {e}")
        raise


def find_cf_zone_id(domain):
    domain = domain.lower().strip()
    zone_search = cf_request("GET", f"/zones?name={domain}")
    if zone_search.get("success") and zone_search.get("result"):
        return zone_search["result"][0]["id"]
    return None


def ensure_cf_zone(domain, steps=None):
    cf_account = get_config_value("CF_ACCOUNT_ID")
    zone_id = find_cf_zone_id(domain)
    if zone_id:
        if steps is not None:
            steps.append(f"Found existing Cloudflare Zone (ID: {zone_id})")
        return zone_id

    if steps is not None:
        steps.append("Querying Cloudflare for existing Zone...")
        steps.append("Creating new Cloudflare Zone...")
    zone_create = cf_request(
        "POST",
        "/zones",
        {
            "name": domain,
            "account": {"id": cf_account},
            "jump_start": True,
        },
    )
    if not zone_create.get("success"):
        err_msg = zone_create.get("errors", [{}])[0].get(
            "message", "Unknown Cloudflare error"
        )
        raise ValueError(f"Cloudflare Zone creation failed: {err_msg}")
    zone_id = zone_create["result"]["id"]
    if steps is not None:
        steps.append(f"Created new Cloudflare Zone (ID: {zone_id})")
    return zone_id


def fetch_cf_dns_sets(zone_id):
    cf_dns_search = cf_request("GET", f"/zones/{zone_id}/dns_records?per_page=100")
    existing_records = (
        cf_dns_search.get("result", []) if cf_dns_search.get("success") else []
    )
    existing_mx = set()
    existing_txt = set()
    for rec in existing_records:
        rtype = rec.get("type")
        rname = rec.get("name", "").lower().rstrip(".")
        rcontent = rec.get("content", "").strip('"')
        if rtype == "MX":
            existing_mx.add((rname, rcontent.lower(), rec.get("priority")))
        elif rtype == "TXT":
            existing_txt.add((rname, rcontent))
    return existing_mx, existing_txt, existing_records
