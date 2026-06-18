from flask import Blueprint, request, jsonify

from utils.validators import validate_domain
from utils.auth_helpers import require_admin, require_permission, require_any_permission, get_current_user, is_user_admin
from models.db import load_domain_mapping
from services.mxroute import mx_request, mx_request_raw, audited_mx

domains_bp = Blueprint("domains", __name__)


@domains_bp.route('/api/domains', methods=['GET'])
@domains_bp.route('/get-domains', methods=['GET'])  # backward compat
def get_domains():
    user = get_current_user()
    res, status = mx_request_raw("GET", "/domains")
    if status == 200 and user and not is_user_admin(user):
        email_val = user.get("email")
        email = email_val.lower() if isinstance(email_val, str) else ""
        mapping = load_domain_mapping()
        allowed = [d.lower() for d in mapping.get(email, [])]
        filtered_data = [d for d in res.get("data", []) if d.lower() in allowed]
        res["data"] = filtered_data
    return jsonify(res), status


@domains_bp.route('/api/domains', methods=['POST'])
@require_admin
def create_domain():
    data = request.json or {}
    domain = data.get("domain")
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
    return audited_mx("POST", "/domains", request.json, "domain.create", target=domain)


@domains_bp.route('/api/domains/<domain>', methods=['GET'])
@require_any_permission("dashboard", "emails", "forwarders", "spam", "dns")
def get_domain_details(domain):
    return mx_request("GET", f"/domains/{domain}")


@domains_bp.route('/api/domains/<domain>', methods=['DELETE'])
@require_admin
def delete_domain(domain):
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
    return audited_mx("DELETE", f"/domains/{domain}", None, "domain.delete", target=domain)


@domains_bp.route('/api/domains/<domain>/mail-status', methods=['PATCH'])
@require_admin
def set_mail_status(domain):
    return audited_mx("PATCH", f"/domains/{domain}/mail-status", request.json, "domain.mail_status", target=domain)


@domains_bp.route('/api/verification-key', methods=['GET'])
@require_admin
def get_verification_key():
    return mx_request("GET", "/verification-key")


# --- DOMAIN POINTERS ---

@domains_bp.route('/api/domains/<domain>/pointers', methods=['GET'])
@require_any_permission("forwarders", "dashboard")
def list_pointers(domain):
    return mx_request("GET", f"/domains/{domain}/pointers")


@domains_bp.route('/api/domains/<domain>/pointers', methods=['POST'])
@require_permission("forwarders")
def create_pointer(domain):
    return audited_mx("POST", f"/domains/{domain}/pointers", request.json, "pointer.create", target=domain)


@domains_bp.route('/api/domains/<domain>/pointers/<pointer>', methods=['DELETE'])
@require_permission("forwarders")
def delete_pointer(domain, pointer):
    return audited_mx("DELETE", f"/domains/{domain}/pointers/{pointer}", None, "pointer.delete", target=f"{pointer}@{domain}")
