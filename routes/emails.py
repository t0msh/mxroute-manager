from flask import Blueprint, request, jsonify

from utils.validators import validate_domain, validate_username
from utils.auth_helpers import require_domain_access, require_compat_domain_access
from services.mxroute import mx_request, audited_mx

emails_bp = Blueprint("emails", __name__)


# --- EMAIL ACCOUNTS ---

@emails_bp.route('/api/domains/<domain>/email-accounts', methods=['GET'])
@emails_bp.route('/list-emails/<domain>', methods=['GET'])  # backward compat
@require_domain_access
def list_emails(domain):
    return mx_request("GET", f"/domains/{domain}/email-accounts")


@emails_bp.route('/api/domains/<domain>/email-accounts', methods=['POST'])
@require_domain_access
def create_email_api(domain):
    data = request.json or {}
    username = data.get("username")
    if not validate_username(username):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400
    return audited_mx("POST", f"/domains/{domain}/email-accounts", request.json, "mailbox.create", target=f"{username}@{domain}")


@emails_bp.route('/create-email', methods=['POST'])  # backward compat (expects Form)
def create_email_compat():
    domain = request.form.get('domain')
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400

    email_username = request.form.get('user')
    if not validate_username(email_username):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400

    denied = require_compat_domain_access(domain)
    if denied:
        return denied

    password = request.form.get('password')
    payload = {
        "username": email_username,
        "password": password,
        "quota": 0
    }
    return audited_mx("POST", f"/domains/{domain}/email-accounts", payload, "mailbox.create", target=f"{email_username}@{domain}")


@emails_bp.route('/api/domains/<domain>/email-accounts/<user>', methods=['GET'])
@require_domain_access
def get_email_account(domain, user):
    return mx_request("GET", f"/domains/{domain}/email-accounts/{user}")


@emails_bp.route('/api/domains/<domain>/email-accounts/<user>', methods=['PATCH'])
@require_domain_access
def update_email_account(domain, user):
    if not validate_username(user):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400
    payload = request.json or {}
    if "password" in payload:
        action = "mailbox.password_update"
    elif "suspended" in payload:
        action = "mailbox.suspend" if payload.get("suspended") else "mailbox.unsuspend"
    elif "quota" in payload or "limit" in payload:
        action = "mailbox.quota_update"
    else:
        action = "mailbox.update"
    return audited_mx("PATCH", f"/domains/{domain}/email-accounts/{user}", payload, action, target=f"{user}@{domain}")


@emails_bp.route('/update-password', methods=['POST'])  # backward compat (expects Form)
def update_password_compat():
    domain = request.form.get('domain')
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400

    email_username = request.form.get('user')
    if not validate_username(email_username):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400

    denied = require_compat_domain_access(domain)
    if denied:
        return denied

    password = request.form.get('password')
    payload = {"password": password}
    return audited_mx("PATCH", f"/domains/{domain}/email-accounts/{email_username}", payload, "mailbox.password_update", target=f"{email_username}@{domain}")


@emails_bp.route('/api/domains/<domain>/email-accounts/<user>', methods=['DELETE'])
@require_domain_access
def delete_email_api(domain, user):
    if not validate_username(user):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400
    return audited_mx("DELETE", f"/domains/{domain}/email-accounts/{user}", None, "mailbox.delete", target=f"{user}@{domain}")


@emails_bp.route('/delete-email', methods=['POST'])  # backward compat (expects Form)
def delete_email_compat():
    domain = request.form.get('domain')
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400

    email_username = request.form.get('user')
    if not validate_username(email_username):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400

    denied = require_compat_domain_access(domain)
    if denied:
        return denied

    return audited_mx("DELETE", f"/domains/{domain}/email-accounts/{email_username}", None, "mailbox.delete", target=f"{email_username}@{domain}")


# --- EMAIL FORWARDERS ---

@emails_bp.route('/api/domains/<domain>/forwarders', methods=['GET'])
@require_domain_access
def list_forwarders(domain):
    return mx_request("GET", f"/domains/{domain}/forwarders")


@emails_bp.route('/api/domains/<domain>/forwarders', methods=['POST'])
@require_domain_access
def create_forwarder(domain):
    data = request.json or {}
    alias = data.get("alias", "")
    return audited_mx("POST", f"/domains/{domain}/forwarders", request.json, "forwarder.create", target=f"{alias}@{domain}")


@emails_bp.route('/api/domains/<domain>/forwarders/<alias>', methods=['DELETE'])
@require_domain_access
def delete_forwarder(domain, alias):
    return audited_mx("DELETE", f"/domains/{domain}/forwarders/{alias}", None, "forwarder.delete", target=f"{alias}@{domain}")


# --- CATCH-ALL ---

@emails_bp.route('/api/domains/<domain>/catch-all', methods=['GET'])
@require_domain_access
def get_catch_all(domain):
    return mx_request("GET", f"/domains/{domain}/catch-all")


@emails_bp.route('/api/domains/<domain>/catch-all', methods=['PATCH'])
@require_domain_access
def update_catch_all(domain):
    return audited_mx("PATCH", f"/domains/{domain}/catch-all", request.json, "catchall.update", target=domain)
