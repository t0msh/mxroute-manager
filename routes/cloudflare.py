from flask import Blueprint, request, jsonify

from utils.validators import validate_domain
from utils.auth_helpers import require_admin, require_any_permission
from models.db import get_config_value, get_dmarc_record
from services.cloudflare import (
    cf_is_configured,
    ensure_cf_zone,
    fetch_cf_dns_sets,
    deploy_dns_record_to_cf,
    build_setup_health,
    deploy_missing_dns_to_cf,
    MAIL_DNS_RECORD_TYPES,
)
from services.mxroute import (
    get_mxroute_verification_record,
    get_mxroute_dns_data,
    inject_dmarc,
    register_domain_on_mxroute,
    mx_request,
    mx_request_raw,
    get_domain_mail_hosting,
    audit,
)
from services.dns_health import check_dns_health, apply_mail_hosting_context

cloudflare_bp = Blueprint("cloudflare", __name__)


@cloudflare_bp.route('/api/cloudflare/status', methods=['GET'])
@require_admin
def get_cf_status():
    return jsonify({
        "success": True,
        "configured": cf_is_configured()
    })


@cloudflare_bp.route('/api/cloudflare/setup', methods=['POST'])
@require_admin
def cloudflare_setup():
    data = request.json or {}
    domain = data.get("domain")
    if not domain or not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400

    if not cf_is_configured():
        return jsonify({"success": False, "error": {"message": "Cloudflare credentials not configured"}}), 400

    steps = []
    domain = domain.lower().strip()

    try:
        zone_id = ensure_cf_zone(domain, steps)
        verification_record = get_mxroute_verification_record()
        if not verification_record:
            return jsonify({"success": False, "error": {"message": "Failed to get verification key from MXroute"}, "steps": steps}), 500

        steps.append("Fetching existing DNS records from Cloudflare...")
        existing_mx, existing_txt, existing_records = fetch_cf_dns_sets(zone_id)

        steps.append("Injecting DNS verification TXT record into Cloudflare...")
        deploy_dns_record_to_cf(
            domain, zone_id, "verification", None, verification_record,
            existing_mx, existing_txt, existing_records, steps,
        )

        steps.append("Registering domain with MXroute platform...")
        register_domain_on_mxroute(domain, steps)

        steps.append("Retrieving MX/SPF/DKIM profiles from MXroute...")
        mx_dns_data = get_mxroute_dns_data(domain)
        if not mx_dns_data:
            return jsonify({"success": False, "error": {"message": "Failed to fetch MXroute DNS configurations"}, "steps": steps}), 500

        steps.append("Deploying mail service records to Cloudflare nameservers...")
        for record_type in MAIL_DNS_RECORD_TYPES:
            deploy_dns_record_to_cf(
                domain, zone_id, record_type, mx_dns_data, verification_record,
                existing_mx, existing_txt, existing_records, steps,
            )

        steps.append("Domain setup complete! All MXroute and Cloudflare settings active.")
        audit("cloudflare.setup", target=domain, steps=len(steps))
        return jsonify({"success": True, "steps": steps})

    except Exception as e:
        return jsonify({"success": False, "error": {"message": str(e)}, "steps": steps}), 500


@cloudflare_bp.route('/api/domains/<domain>/dns/setup-health', methods=['GET'])
@require_admin
def get_dns_setup_health(domain):
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
    health = build_setup_health(domain)
    if not health:
        return jsonify({"success": False, "error": {"message": "Failed to fetch DNS expectations from MXroute"}}), 502
    return jsonify({"success": True, "data": health})


@cloudflare_bp.route('/api/domains/<domain>/dns/fix', methods=['POST'])
@require_admin
def fix_domain_dns(domain):
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
    if not cf_is_configured():
        return jsonify({"success": False, "error": {"message": "Cloudflare credentials not configured"}}), 400

    data = request.json or {}
    record_types = data.get("records")

    try:
        result = deploy_missing_dns_to_cf(domain, record_types)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": {"message": str(e)}}), 400


@cloudflare_bp.route('/api/domains/<domain>/dns', methods=['GET'])
@require_any_permission("dashboard", "dns")
def get_dns_info(domain):
    res, status = mx_request_raw("GET", f"/domains/{domain}/dns")
    if status == 200 and isinstance(res, dict) and res.get("success"):
        res["data"] = inject_dmarc(res.get("data"))
    return jsonify(res), status


@cloudflare_bp.route('/api/domains/<domain>/dns/health', methods=['GET'])
@require_any_permission("dashboard", "dns")
def get_dns_health(domain):
    mx_dns_res, mx_dns_status = mx_request_raw("GET", f"/domains/{domain}/dns")
    if mx_dns_status != 200:
        return jsonify({"success": False, "error": {"message": "Failed to fetch DNS expectations from MXroute"}}), 502

    verification_record = None
    verify_res, verify_status = mx_request_raw("GET", "/verification-key")
    if verify_status == 200:
        verification_record = verify_res.get("data", {}).get("record")

    health = check_dns_health(
        domain,
        mx_dns_res.get("data", {}),
        verification_record=verification_record,
        dmarc_expected=get_dmarc_record(),
    )
    health = apply_mail_hosting_context(health, get_domain_mail_hosting(domain))

    _, mx_status = mx_request_raw("GET", "/domains")
    health["mxroute_reachable"] = mx_status == 200

    return jsonify({"success": True, "data": health})
