from dataclasses import dataclass

from models.db_dmarc import get_dmarc_record_for_domain
from services.cloudflare_api import (
    cf_is_configured,
    cf_request,
    ensure_cf_zone,
    fetch_cf_dns_sets,
)
from services.cloudflare_constants import (
    DEPLOYABLE_RECORD_TYPES,
    MAIL_DNS_RECORD_TYPES,
    get_webmail_target,
    mail_host,
    webmail_host,
)
from services.cloudflare_health import build_setup_health
from services.cloudflare_records import cf_upsert_cname, cf_upsert_txt
from services.dns_health import dkim_record_parts
from services.mxroute import (
    audit,
    get_mxroute_dns_data,
    get_mxroute_verification_record,
)


@dataclass
class CfDeployContext:
    domain: str
    zone_id: str
    mx_dns_data: dict | None
    verification_record: dict | None
    existing_mx: set
    existing_txt: set
    existing_records: list
    steps: list | None = None

    @property
    def domain_lower(self) -> str:
        return self.domain.lower()

    def dns_state(self) -> dict:
        return {
            "existing_records": self.existing_records,
            "existing_txt": self.existing_txt,
            "steps": self.steps,
        }


def _deploy_mail(ctx: CfDeployContext) -> str:
    target = get_webmail_target()
    if not target:
        if ctx.steps is not None:
            ctx.steps.append("MX_SERVER not configured; skipping mail CNAME")
        return "skipped"
    return cf_upsert_cname(
        ctx.zone_id,
        "mail",
        mail_host(ctx.domain),
        target,
        ctx.existing_records,
        ctx.steps,
        proxied=False,
    )


def _deploy_webmail(ctx: CfDeployContext) -> str:
    target = get_webmail_target()
    if not target:
        if ctx.steps is not None:
            ctx.steps.append("MX_SERVER not configured; skipping webmail CNAME")
        return "skipped"
    return cf_upsert_cname(
        ctx.zone_id,
        "webmail",
        webmail_host(ctx.domain),
        target,
        ctx.existing_records,
        ctx.steps,
        proxied=False,
    )


def _deploy_verification(ctx: CfDeployContext) -> str:
    if not ctx.verification_record:
        raise ValueError("Failed to get verification key from MXroute")
    verify_name = ctx.verification_record.get("name")
    verify_value = ctx.verification_record.get("value")
    verify_name_full = f"{verify_name}.{ctx.domain}".lower()
    return cf_upsert_txt(
        ctx.zone_id,
        verify_name,
        verify_name_full,
        verify_value,
        ctx.dns_state(),
        {
            "skipped": "Verification TXT record already correct in Cloudflare",
            "added": "Verification TXT record deployed successfully",
            "updated": "Verification TXT record updated in Cloudflare",
        },
    )


def _deploy_mx(ctx: CfDeployContext) -> str:
    if not ctx.mx_dns_data.get("mx_records"):
        if ctx.steps is not None:
            ctx.steps.append("No MX data available from MXroute (skipping)")
        return "skipped"

    added = False
    for mx in ctx.mx_dns_data["mx_records"]:
        mx_host = mx["hostname"].lower().rstrip(".")
        mx_priority = mx["priority"]
        has_mx = any(
            rname == ctx.domain_lower
            and rcontent == mx_host
            and int(rpriority or 0) == int(mx_priority or 0)
            for rname, rcontent, rpriority in ctx.existing_mx
        )
        if not has_mx:
            cf_request(
                "POST",
                f"/zones/{ctx.zone_id}/dns_records",
                {
                    "type": "MX",
                    "name": "@",
                    "content": mx["hostname"],
                    "priority": mx["priority"],
                    "ttl": 3600,
                },
            )
            added = True
    if ctx.steps is not None:
        ctx.steps.append(
            "MX records configured" if added else "MX records already exist (skipping)"
        )
    return "added" if added else "skipped"


def _deploy_spf(ctx: CfDeployContext) -> str:
    if not ctx.mx_dns_data.get("spf"):
        if ctx.steps is not None:
            ctx.steps.append("No SPF data available from MXroute (skipping)")
        return "skipped"
    spf_val = ctx.mx_dns_data["spf"]["value"]
    return cf_upsert_txt(
        ctx.zone_id,
        "@",
        ctx.domain_lower,
        spf_val,
        ctx.dns_state(),
        {
            "skipped": "SPF record already correct in Cloudflare",
            "added": "SPF record configured",
            "updated": "SPF record updated in Cloudflare",
        },
    )


def _deploy_dkim(ctx: CfDeployContext) -> str:
    if not ctx.mx_dns_data.get("dkim"):
        if ctx.steps is not None:
            ctx.steps.append("No DKIM data available from MXroute (skipping)")
        return "skipped"
    dkim_host_part, dkim_name_full = dkim_record_parts(
        ctx.mx_dns_data["dkim"], ctx.domain
    )
    dkim_val = ctx.mx_dns_data["dkim"]["value"]
    return cf_upsert_txt(
        ctx.zone_id,
        dkim_host_part,
        dkim_name_full,
        dkim_val,
        ctx.dns_state(),
        {
            "skipped": "DKIM record already correct in Cloudflare",
            "added": "DKIM record configured",
            "updated": "DKIM record updated in Cloudflare (previous value did not match MXroute)",
        },
    )


def _deploy_dmarc(ctx: CfDeployContext) -> str:
    dmarc_val = get_dmarc_record_for_domain(ctx.domain)
    dmarc_name_full = f"_dmarc.{ctx.domain}".lower()
    return cf_upsert_txt(
        ctx.zone_id,
        "_dmarc",
        dmarc_name_full,
        dmarc_val,
        ctx.dns_state(),
        {
            "skipped": "DMARC record already correct in Cloudflare",
            "added": "DMARC record configured",
            "updated": "DMARC record updated in Cloudflare",
        },
    )


_MAIL_DEPLOY_HANDLERS = {
    "mx": _deploy_mx,
    "spf": _deploy_spf,
    "dkim": _deploy_dkim,
    "dmarc": _deploy_dmarc,
}


def deploy_dns_record_to_cf(ctx: CfDeployContext, record_type: str) -> str:
    """Deploy a single DNS record type to Cloudflare. Returns 'added' or 'skipped'."""
    if record_type == "webmail":
        return _deploy_webmail(ctx)
    if record_type == "mail":
        return _deploy_mail(ctx)
    if record_type == "verification":
        return _deploy_verification(ctx)

    if record_type not in MAIL_DNS_RECORD_TYPES:
        raise ValueError(f"Unknown record type: {record_type}")

    if not ctx.mx_dns_data:
        raise ValueError(
            "Mail DNS records require the domain to be registered on MXroute first"
        )

    handler = _MAIL_DEPLOY_HANDLERS.get(record_type)
    if handler:
        return handler(ctx)

    if ctx.steps is not None:
        ctx.steps.append(
            f"No {record_type.upper()} data available from MXroute (skipping)"
        )
    return "skipped"


def deploy_missing_dns_to_cf(domain, record_types=None):
    """Fix missing DNS records in Cloudflare for a domain."""
    steps = []
    if not cf_is_configured():
        raise ValueError("Cloudflare credentials not configured")

    health = build_setup_health(domain)
    if not health:
        raise ValueError("Failed to build DNS health state")

    if record_types is None:
        record_types = [
            key
            for key, check in health["checks"].items()
            if check["status"] in ("warn", "fail")
        ]
    else:
        record_types = [r.lower() for r in record_types]

    mail_requested = [r for r in record_types if r in MAIL_DNS_RECORD_TYPES]
    if mail_requested and not health["on_mxroute"]:
        raise ValueError(
            "Mail, MX, SPF, DKIM, and DMARC records require the domain to be registered on MXroute first. "
            "Complete Step 3, then return to Step 2."
        )

    if not record_types:
        return {
            "fixed": [],
            "skipped": list(health["checks"].keys()),
            "steps": ["All DNS records already look good"],
        }

    steps.append("Fetching existing DNS records from Cloudflare...")
    zone_id = ensure_cf_zone(domain, steps)
    existing_mx, existing_txt, existing_records = fetch_cf_dns_sets(zone_id)

    verification_record = get_mxroute_verification_record()
    mx_dns_data = get_mxroute_dns_data(domain) if health["on_mxroute"] else None
    ctx = CfDeployContext(
        domain,
        zone_id,
        mx_dns_data,
        verification_record,
        existing_mx,
        existing_txt,
        existing_records,
        steps,
    )

    fixed = []
    skipped = []
    for record_type in record_types:
        if record_type not in DEPLOYABLE_RECORD_TYPES:
            continue
        check = health["checks"].get(record_type, {})
        if check.get("status") == "pass":
            skipped.append(record_type)
            continue
        if check.get("status") == "pending":
            skipped.append(record_type)
            continue
        result = deploy_dns_record_to_cf(ctx, record_type)
        if result in ("added", "updated"):
            fixed.append(record_type)
        else:
            skipped.append(record_type)

    if fixed:
        audit("dns.fix", target=domain, records=fixed, outcome="updated")
    else:
        audit("dns.fix", target=domain, records=[], outcome="no_changes")
    return {"fixed": fixed, "skipped": skipped, "steps": steps}
