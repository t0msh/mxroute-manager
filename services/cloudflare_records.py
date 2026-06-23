from services.cloudflare_api import cf_request
from services.dns_health import _normalize_txt


def cf_upsert_txt(zone_id, cf_name, fqdn, content, dns_state, log_messages):
    """Create or update a TXT record when missing or incorrect. Returns added, updated, or skipped."""
    existing_records = dns_state["existing_records"]
    existing_txt = dns_state["existing_txt"]
    steps = dns_state.get("steps")
    fqdn = fqdn.lower().rstrip(".")
    expected_norm = _normalize_txt(content)
    at_name = [
        rec
        for rec in existing_records
        if rec.get("type") == "TXT" and rec.get("name", "").lower().rstrip(".") == fqdn
    ]

    for rec in at_name:
        if _normalize_txt(rec.get("content", "")) == expected_norm:
            if steps is not None:
                steps.append(log_messages["skipped"])
            return "skipped"

    payload = {"type": "TXT", "name": cf_name, "content": content, "ttl": 3600}

    if at_name:
        result = cf_request(
            "PUT", f"/zones/{zone_id}/dns_records/{at_name[0]['id']}", payload
        )
        if not result.get("success"):
            err_msg = result.get("errors", [{}])[0].get(
                "message", "Unknown Cloudflare error"
            )
            raise ValueError(f"Failed to update TXT record at {fqdn}: {err_msg}")
        for extra in at_name[1:]:
            cf_request("DELETE", f"/zones/{zone_id}/dns_records/{extra['id']}")
        existing_txt.difference_update({(n, c) for n, c in existing_txt if n == fqdn})
        existing_txt.add((fqdn, content))
        if steps is not None:
            steps.append(log_messages["updated"])
        return "updated"

    result = cf_request("POST", f"/zones/{zone_id}/dns_records", payload)
    if not result.get("success"):
        err_msg = result.get("errors", [{}])[0].get(
            "message", "Unknown Cloudflare error"
        )
        raise ValueError(f"Failed to add TXT record at {fqdn}: {err_msg}")
    existing_txt.add((fqdn, content))
    if steps is not None:
        steps.append(log_messages["added"])
    return "added"


def cf_upsert_cname(
    zone_id, cf_name, fqdn, target, existing_records, steps, proxied=True
):
    fqdn = fqdn.lower().rstrip(".")
    target = target.lower().rstrip(".")
    at_name = [
        rec
        for rec in existing_records
        if rec.get("type") == "CNAME"
        and rec.get("name", "").lower().rstrip(".") == fqdn
    ]

    for rec in at_name:
        current_target = rec.get("content", "").lower().rstrip(".")
        if current_target == target and bool(rec.get("proxied")) == bool(proxied):
            if steps is not None:
                steps.append(f"CNAME {fqdn} already points to {target}")
            return "skipped"

    payload = {
        "type": "CNAME",
        "name": cf_name,
        "content": target,
        "ttl": 3600,
        "proxied": bool(proxied),
    }

    if at_name:
        result = cf_request(
            "PUT", f"/zones/{zone_id}/dns_records/{at_name[0]['id']}", payload
        )
        if not result.get("success"):
            err_msg = result.get("errors", [{}])[0].get(
                "message", "Unknown Cloudflare error"
            )
            raise ValueError(f"Failed to update CNAME at {fqdn}: {err_msg}")
        for extra in at_name[1:]:
            cf_request("DELETE", f"/zones/{zone_id}/dns_records/{extra['id']}")
        if steps is not None:
            steps.append(f"Updated CNAME {fqdn} → {target}")
        return "updated"

    result = cf_request("POST", f"/zones/{zone_id}/dns_records", payload)
    if not result.get("success"):
        err_msg = result.get("errors", [{}])[0].get(
            "message", "Unknown Cloudflare error"
        )
        raise ValueError(f"Failed to add CNAME at {fqdn}: {err_msg}")
    if steps is not None:
        steps.append(f"Added CNAME {fqdn} → {target}")
    return "added"
