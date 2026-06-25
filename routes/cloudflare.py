from flask import Blueprint, request, jsonify

from models.db_dmarc import (
    clear_domain_dmarc_policy,
    dmarc_check_options,
    dmarc_policy_payload,
    set_domain_dmarc_policy,
)
from utils.validators import validate_domain, validate_dmarc_record, nested_dict_get
from utils.auth_helpers import require_admin, require_any_permission, require_permission
from services.cloudflare import (
    cf_is_configured,
    ensure_cf_zone,
    fetch_cf_dns_sets,
    deploy_dns_record_to_cf,
    CfDeployContext,
    build_setup_health,
    deploy_missing_dns_to_cf,
    MAIL_DNS_RECORD_TYPES,
    _mail_health_check,
)
from services.cloudflare_bulk import fix_dns_bulk
from services.mxroute import (
    get_mxroute_verification_record,
    get_mxroute_dns_data,
    inject_dmarc,
    register_domain_on_mxroute,
    mx_request_raw,
    get_domain_mail_hosting,
    audit,
)
from services.dns_health import (
    check_dns_health,
    apply_mail_hosting_context,
    overall_from_checks,
)

cloudflare_bp = Blueprint("cloudflare", __name__)


@cloudflare_bp.route("/api/cloudflare/status", methods=["GET"])
@require_admin
def get_cf_status():
    return jsonify({"success": True, "configured": cf_is_configured()})


@cloudflare_bp.route("/api/cloudflare/setup", methods=["POST"])
@require_admin
def cloudflare_setup():
    data = request.json or {}
    domain = data.get("domain")
    if not domain or not validate_domain(domain):
        return jsonify(
            {"success": False, "error": {"message": "Invalid domain name format"}}
        ), 400

    if not cf_is_configured():
        return jsonify(
            {
                "success": False,
                "error": {"message": "Cloudflare credentials not configured"},
            }
        ), 400

    steps = []
    domain = domain.lower().strip()

    try:
        zone_id = ensure_cf_zone(domain, steps)
        verification_record = get_mxroute_verification_record()
        if not verification_record:
            return jsonify(
                {
                    "success": False,
                    "error": {"message": "Failed to get verification key from MXroute"},
                    "steps": steps,
                }
            ), 500

        steps.append("Fetching existing DNS records from Cloudflare...")
        existing_mx, existing_txt, existing_records = fetch_cf_dns_sets(zone_id)
        deploy_ctx = CfDeployContext(
            domain,
            zone_id,
            None,
            verification_record,
            existing_mx,
            existing_txt,
            existing_records,
            steps,
        )

        steps.append("Injecting DNS verification TXT record into Cloudflare...")
        deploy_dns_record_to_cf(deploy_ctx, "verification")

        steps.append("Registering domain with MXroute platform...")
        register_domain_on_mxroute(domain, steps)

        steps.append("Retrieving MX/SPF/DKIM profiles from MXroute...")
        mx_dns_data = get_mxroute_dns_data(domain)
        if not mx_dns_data:
            return jsonify(
                {
                    "success": False,
                    "error": {"message": "Failed to fetch MXroute DNS configurations"},
                    "steps": steps,
                }
            ), 500

        steps.append("Deploying mail service records to Cloudflare nameservers...")
        deploy_ctx.mx_dns_data = mx_dns_data
        for record_type in MAIL_DNS_RECORD_TYPES:
            deploy_dns_record_to_cf(deploy_ctx, record_type)

        steps.append(
            "Domain setup complete! All MXroute and Cloudflare settings active."
        )
        audit("cloudflare.setup", target=domain, steps=len(steps))
        return jsonify({"success": True, "steps": steps})

    except Exception as e:
        return jsonify(
            {"success": False, "error": {"message": str(e)}, "steps": steps}
        ), 500


@cloudflare_bp.route("/api/domains/<domain>/dns/setup-health", methods=["GET"])
@require_permission("dns")
def get_dns_setup_health(domain):
    if not validate_domain(domain):
        return jsonify(
            {"success": False, "error": {"message": "Invalid domain name format"}}
        ), 400
    health = build_setup_health(domain)
    if not health:
        return jsonify(
            {
                "success": False,
                "error": {"message": "Failed to fetch DNS expectations from MXroute"},
            }
        ), 502
    return jsonify({"success": True, "data": health})


@cloudflare_bp.route("/api/cloudflare/dns/fix-bulk", methods=["POST"])
@require_admin
def fix_dns_bulk_route():
    if not cf_is_configured():
        return jsonify(
            {
                "success": False,
                "error": {"message": "Cloudflare credentials not configured"},
            }
        ), 400

    data = request.json or {}
    domains = data.get("domains")
    if domains is not None and not isinstance(domains, list):
        return jsonify(
            {"success": False, "error": {"message": "domains must be a list"}},
        ), 400

    record_types = data.get("records")
    if record_types is not None and not isinstance(record_types, list):
        return jsonify(
            {"success": False, "error": {"message": "records must be a list"}},
        ), 400

    only_unhealthy = bool(data.get("only_unhealthy"))
    if not domains:
        res, status = mx_request_raw("GET", "/domains")
        if status != 200:
            return jsonify(
                {
                    "success": False,
                    "error": {"message": "Failed to list domains from MXroute"},
                }
            ), 502
        domains = res.get("data") or []

    try:
        result = fix_dns_bulk(
            domains,
            record_types,
            only_unhealthy=only_unhealthy,
        )
        fixed_domains = [
            domain
            for domain, payload in result.get("results", {}).items()
            if payload.get("success") and payload.get("fixed")
        ]
        audit(
            "dns.fix_bulk",
            target=f"{len(result.get('domains', []))} domains",
            details={
                "only_unhealthy": only_unhealthy,
                "fixed_domains": fixed_domains,
                "count": len(fixed_domains),
            },
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": {"message": str(e)}}), 400


@cloudflare_bp.route("/api/domains/<domain>/dns/fix", methods=["POST"])
@require_permission("dns")
def fix_domain_dns(domain):
    if not validate_domain(domain):
        return jsonify(
            {"success": False, "error": {"message": "Invalid domain name format"}}
        ), 400
    if not cf_is_configured():
        return jsonify(
            {
                "success": False,
                "error": {"message": "Cloudflare credentials not configured"},
            }
        ), 400

    data = request.json or {}
    record_types = data.get("records")

    try:
        result = deploy_missing_dns_to_cf(domain, record_types)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": {"message": str(e)}}), 400


@cloudflare_bp.route("/api/domains/<domain>/dns", methods=["GET"])
@require_any_permission("dashboard", "dns")
def get_dns_info(domain):
    res, status = mx_request_raw("GET", f"/domains/{domain}/dns")
    if status == 200 and isinstance(res, dict) and res.get("success"):
        res["data"] = inject_dmarc(res.get("data"), domain)
    return jsonify(res), status


@cloudflare_bp.route("/api/domains/<domain>/dmarc-policy", methods=["GET"])
@require_permission("dns")
def get_domain_dmarc_policy_route(domain):
    if not validate_domain(domain):
        return jsonify(
            {"success": False, "error": {"message": "Invalid domain name format"}}
        ), 400
    return jsonify(
        {
            "success": True,
            "data": dmarc_policy_payload(domain),
        }
    )


@cloudflare_bp.route("/api/domains/<domain>/dmarc-policy", methods=["PATCH"])
@require_permission("dns")
def update_domain_dmarc_policy_route(domain):
    if not validate_domain(domain):
        return jsonify(
            {"success": False, "error": {"message": "Invalid domain name format"}}
        ), 400

    data = request.json or {}
    if "dmarc_record" not in data:
        return jsonify(
            {"success": False, "error": {"message": "dmarc_record is required"}},
        ), 400

    raw_value = data.get("dmarc_record")
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        clear_domain_dmarc_policy(domain)
        audit("dns.dmarc_policy_clear", target=domain)
        return jsonify({"success": True, "data": dmarc_policy_payload(domain)})

    if not isinstance(raw_value, str) or not validate_dmarc_record(raw_value):
        return jsonify(
            {
                "success": False,
                "error": {
                    "message": "Invalid DMARC record (expected v=DMARC1 with a p= policy)"
                },
            }
        ), 400

    set_domain_dmarc_policy(domain, raw_value)
    audit("dns.dmarc_policy_update", target=domain)
    return jsonify({"success": True, "data": dmarc_policy_payload(domain)})


@cloudflare_bp.route("/api/domains/<domain>/dns/health", methods=["GET"])
@require_any_permission("dashboard", "dns")
def get_dns_health(domain):
    mx_dns_res, mx_dns_status = mx_request_raw("GET", f"/domains/{domain}/dns")
    if mx_dns_status != 200:
        return jsonify(
            {
                "success": False,
                "error": {"message": "Failed to fetch DNS expectations from MXroute"},
            }
        ), 502

    verification_record = None
    verify_res, verify_status = mx_request_raw("GET", "/verification-key")
    if verify_status == 200:
        verification_record = nested_dict_get(verify_res, "data", "record")

    health = check_dns_health(
        domain,
        mx_dns_res.get("data", {}),
        verification_record=verification_record,
        **dmarc_check_options(domain),
    )
    health["checks"]["mail"] = _mail_health_check(domain)
    health["overall"] = overall_from_checks(health["checks"])
    health = apply_mail_hosting_context(health, get_domain_mail_hosting(domain))
    health["dmarc_policy"] = dmarc_policy_payload(domain)

    _, mx_status = mx_request_raw("GET", "/domains")
    health["mxroute_reachable"] = mx_status == 200

    return jsonify({"success": True, "data": health})
