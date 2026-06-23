from models.db import build_portal_host, get_reset_portal_cname_target
from services.cloudflare_api import (
    cf_is_configured,
    cf_request,
    ensure_cf_zone,
    fetch_cf_dns_sets,
    find_cf_zone_id,
)
from services.cloudflare_dns import public_dns_resolves
from services.cloudflare_records import cf_upsert_cname
from services.mxroute import audit


def deploy_reset_portal_cname(domain, prefix):
    target = get_reset_portal_cname_target()
    if not target:
        raise ValueError("RESET_PORTAL_CNAME_TARGET is not configured")

    prefix = (prefix or "").strip().lower()
    if not prefix:
        raise ValueError("Subdomain prefix is required")

    domain = domain.lower().strip()
    steps = []
    zone_id = ensure_cf_zone(domain, steps)
    _, _, existing_records = fetch_cf_dns_sets(zone_id)
    fqdn = build_portal_host(prefix, domain)
    result = cf_upsert_cname(
        zone_id, prefix, fqdn, target, existing_records, steps, proxied=True
    )
    audit("reset_portal.dns_deploy", target=domain, host=fqdn, outcome=result)
    return {"host": fqdn, "target": target, "outcome": result, "steps": steps}


def remove_reset_portal_cname(domain, portal_host, steps=None):
    zone_id = find_cf_zone_id(domain)
    if not zone_id:
        if steps is not None:
            steps.append(f"No Cloudflare zone for {domain}; CNAME not removed.")
        return {"outcome": "skipped", "host": portal_host}

    portal_host = portal_host.lower().rstrip(".")
    _, _, records = fetch_cf_dns_sets(zone_id)
    matches = [
        rec
        for rec in records
        if rec.get("type") == "CNAME"
        and rec.get("name", "").lower().rstrip(".") == portal_host
    ]
    if not matches:
        if steps is not None:
            steps.append(f"No Cloudflare CNAME found for {portal_host}.")
        return {"outcome": "skipped", "host": portal_host}

    for rec in matches:
        cf_request("DELETE", f"/zones/{zone_id}/dns_records/{rec['id']}")
    if steps is not None:
        steps.append(f"Removed Cloudflare CNAME {portal_host}")
    audit("reset_portal.dns_remove", target=domain, host=portal_host, outcome="removed")
    return {"outcome": "removed", "host": portal_host}


def _check_reset_portal_dns_cloudflare(host, domain, expected_target):
    if not cf_is_configured():
        return None

    zone_id = find_cf_zone_id(domain)
    if not zone_id:
        return None

    try:
        _, _, records = fetch_cf_dns_sets(zone_id)
    except Exception:
        return None

    host = host.lower().rstrip(".")
    expected_target = expected_target.lower().rstrip(".")
    matches = [
        rec
        for rec in records
        if rec.get("type") == "CNAME"
        and rec.get("name", "").lower().rstrip(".") == host
    ]
    if not matches:
        return {
            "status": "fail",
            "message": f"No CNAME record for {host} in Cloudflare.",
            "host": host,
            "expected_target": expected_target,
            "source": "cloudflare",
        }

    rec = matches[0]
    target = rec.get("content", "").lower().rstrip(".")
    proxied = bool(rec.get("proxied"))
    if target != expected_target:
        return {
            "status": "warn",
            "message": f"Cloudflare CNAME {host} points to {target} (expected {expected_target}).",
            "host": host,
            "targets": [target],
            "expected_target": expected_target,
            "proxied": proxied,
            "source": "cloudflare",
        }

    message = f"Cloudflare CNAME {host} → {expected_target}"
    if proxied:
        message += " (proxied)"
    result = {
        "status": "pass",
        "message": message + ".",
        "host": host,
        "targets": [target],
        "proxied": proxied,
        "source": "cloudflare",
    }
    if not public_dns_resolves(host):
        result["status"] = "warn"
        result["message"] = (
            f"{message}, but public DNS does not resolve {host} yet. "
            "Ensure the domain nameservers point to Cloudflare."
        )
    return result


def check_reset_portal_dns(portal):
    import dns.exception
    import dns.resolver

    if not portal or not portal.get("enabled") or not portal.get("subdomain_prefix"):
        return {"status": "disabled", "message": "Portal is not enabled."}

    host = portal.get("portal_host") or build_portal_host(
        portal["subdomain_prefix"], portal["domain"]
    )
    expected_target = get_reset_portal_cname_target()
    if not expected_target:
        return {
            "status": "unknown",
            "message": "RESET_PORTAL_CNAME_TARGET is not configured.",
        }

    cf_result = _check_reset_portal_dns_cloudflare(
        host, portal["domain"], expected_target
    )
    if cf_result is not None:
        return cf_result

    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = 5.0
        answers = resolver.resolve(host, "CNAME")
        targets = [str(record.target).lower().rstrip(".") for record in answers]
    except dns.resolver.NoResolverConfiguration:
        return {
            "status": "unknown",
            "message": "DNS resolver is not configured on this host.",
            "host": host,
        }
    except (dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, dns.exception.Timeout):
        if public_dns_resolves(host):
            return {
                "status": "pass",
                "message": f"{host} resolves publicly (likely proxied through Cloudflare).",
                "host": host,
                "source": "public",
            }
        return {
            "status": "fail",
            "message": f"{host} does not resolve in public DNS yet.",
            "host": host,
            "expected_target": expected_target,
        }
    except dns.resolver.NoAnswer:
        if public_dns_resolves(host):
            return {
                "status": "pass",
                "message": f"{host} resolves publicly (likely proxied through Cloudflare).",
                "host": host,
                "source": "public",
            }
        return {
            "status": "fail",
            "message": f"No DNS records found for {host} yet.",
            "host": host,
            "expected_target": expected_target,
        }
    except Exception:
        return {
            "status": "unknown",
            "message": f"Could not resolve DNS for {host}.",
            "host": host,
        }

    if expected_target in targets:
        return {
            "status": "pass",
            "message": f"CNAME {host} points to {expected_target}.",
            "host": host,
            "targets": targets,
        }
    return {
        "status": "warn",
        "message": f"CNAME {host} points to {', '.join(targets)} (expected {expected_target}).",
        "host": host,
        "targets": targets,
        "expected_target": expected_target,
    }
