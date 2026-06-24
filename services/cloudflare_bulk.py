"""Bulk DNS repair across multiple domains."""

from concurrent.futures import ThreadPoolExecutor, as_completed

from services.cloudflare import (
    build_setup_health,
    cf_is_configured,
    deploy_missing_dns_to_cf,
)


def _domain_needs_fix(domain):
    health = build_setup_health(domain)
    return bool(health and health.get("overall") != "healthy")


def fix_dns_bulk(domains, record_types=None, *, only_unhealthy=False):
    """Fix DNS for many domains with a capped worker pool."""
    if not cf_is_configured():
        raise ValueError("Cloudflare credentials not configured")

    normalized = [str(domain).lower().strip() for domain in domains or [] if domain]
    if only_unhealthy:
        normalized = [domain for domain in normalized if _domain_needs_fix(domain)]

    if not normalized:
        return {"results": {}, "domains": [], "skipped": "no_domains"}

    results = {}

    def fix_one(domain):
        try:
            payload = deploy_missing_dns_to_cf(domain, record_types)
            return domain, {"success": True, **payload}, None
        except Exception as exc:
            return domain, None, str(exc)

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fix_one, domain): domain for domain in normalized}
        for future in as_completed(futures):
            domain, payload, error = future.result()
            if error:
                results[domain] = {"success": False, "error": error}
            else:
                results[domain] = payload

    return {"domains": normalized, "results": results}
