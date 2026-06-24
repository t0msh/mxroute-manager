from flask import Blueprint, request, jsonify

from utils.validators import validate_domain
from utils.auth_helpers import (
    require_admin,
    require_permission,
    require_any_permission,
    get_current_user,
    is_user_admin,
    has_any_permission,
    get_domain_grants,
)
from models.db import load_domain_mapping, get_fleet_overview_state
from services.mxroute import mx_request, mx_request_raw, audited_mx
from services.fleet_monitor import run_fleet_overview_scan

domains_bp = Blueprint("domains", __name__)


def _user_account_domains(user):
    """Domains the user sees in /api/domains — same filter as get_domains."""
    if not user:
        return []
    email_val = user.get("email")
    email = email_val.lower() if isinstance(email_val, str) else ""
    mapping = load_domain_mapping()
    allowed = [d.lower() for d in mapping.get(email, []) if d != "*"]
    admin_all = is_user_admin(user) or "*" in mapping.get(email, [])

    res, status = mx_request_raw("GET", "/domains")
    if status != 200:
        return sorted(allowed) if not admin_all else []

    domains = [str(domain).lower() for domain in res.get("data", []) if domain]
    if admin_all:
        return sorted(domains)
    allowed_set = set(allowed)
    return sorted(domain for domain in domains if domain in allowed_set)


def _fleet_visible_domains(user):
    if not user:
        return []
    if is_user_admin(user):
        res, status = mx_request_raw("GET", "/domains")
        if status != 200:
            return []
        return sorted(str(domain).lower() for domain in res.get("data", []) if domain)

    grants = get_domain_grants(user)
    visible = []
    for domain in grants:
        if has_any_permission(user, domain, "dashboard", "dns", "emails"):
            visible.append(domain.lower())
    return sorted(visible)


def _fleet_row_for_user(user, domain, cached):
    if not isinstance(cached, dict):
        return {"domain": domain}
    row = {
        "domain": domain,
        "mail_hosting": cached.get("mail_hosting"),
        "dns": cached.get("dns"),
    }
    if has_any_permission(user, domain, "dashboard", "emails"):
        row["mailbox_count"] = cached.get("mailbox_count")
    return row


def _fleet_overview_payload(user):
    state = get_fleet_overview_state()
    cached_domains = state.get("domains") or {}
    domains = [
        _fleet_row_for_user(user, domain, cached_domains.get(domain) or {})
        for domain in _user_account_domains(user)
    ]
    return {
        "last_run_at": state.get("last_run_at"),
        "domains": domains,
    }


@domains_bp.route("/api/fleet/overview", methods=["GET"])
def get_fleet_overview():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": {"message": "Unauthorized"}}), 401
    return jsonify({"success": True, "data": _fleet_overview_payload(user)})


@domains_bp.route("/api/fleet/overview/refresh", methods=["POST"])
def refresh_fleet_overview():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": {"message": "Unauthorized"}}), 401
    if not _user_account_domains(user):
        return jsonify(
            {
                "success": False,
                "error": {"message": "No domains available to refresh"},
            }
        ), 400
    run_fleet_overview_scan()
    return jsonify({"success": True, "data": _fleet_overview_payload(user)})


@domains_bp.route("/api/domains", methods=["GET"])
@domains_bp.route("/get-domains", methods=["GET"])  # backward compat
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


@domains_bp.route("/api/domains", methods=["POST"])
@require_admin
def create_domain():
    data = request.json or {}
    domain = data.get("domain")
    if not validate_domain(domain):
        return jsonify(
            {"success": False, "error": {"message": "Invalid domain name format"}}
        ), 400
    return audited_mx("POST", "/domains", request.json, "domain.create", target=domain)


@domains_bp.route("/api/domains/<domain>", methods=["GET"])
@require_any_permission("dashboard", "emails", "forwarders", "spam", "dns")
def get_domain_details(domain):
    return mx_request("GET", f"/domains/{domain}")


@domains_bp.route("/api/domains/<domain>", methods=["DELETE"])
@require_admin
def delete_domain(domain):
    if not validate_domain(domain):
        return jsonify(
            {"success": False, "error": {"message": "Invalid domain name format"}}
        ), 400
    return audited_mx(
        "DELETE", f"/domains/{domain}", None, "domain.delete", target=domain
    )


@domains_bp.route("/api/domains/<domain>/mail-status", methods=["PATCH"])
@require_admin
def set_mail_status(domain):
    return audited_mx(
        "PATCH",
        f"/domains/{domain}/mail-status",
        request.json,
        "domain.mail_status",
        target=domain,
    )


@domains_bp.route("/api/verification-key", methods=["GET"])
@require_admin
def get_verification_key():
    return mx_request("GET", "/verification-key")


@domains_bp.route("/api/domains/<domain>/pointers", methods=["GET"])
@require_any_permission("forwarders", "dashboard")
def list_pointers(domain):
    return mx_request("GET", f"/domains/{domain}/pointers")


@domains_bp.route("/api/domains/<domain>/pointers", methods=["POST"])
@require_permission("forwarders")
def create_pointer(domain):
    return audited_mx(
        "POST",
        f"/domains/{domain}/pointers",
        request.json,
        "pointer.create",
        target=domain,
    )


@domains_bp.route("/api/domains/<domain>/pointers/<pointer>", methods=["DELETE"])
@require_permission("forwarders")
def delete_pointer(domain, pointer):
    return audited_mx(
        "DELETE",
        f"/domains/{domain}/pointers/{pointer}",
        None,
        "pointer.delete",
        target=f"{pointer}@{domain}",
    )
