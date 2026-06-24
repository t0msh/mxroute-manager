from flask import Blueprint, request, jsonify

from models.db import (
    delete_recovery_email,
    get_recovery_map,
    set_recovery_email,
)
from utils.validators import validate_username, validate_recovery_email
from utils.auth_helpers import (
    get_current_user,
    require_permission,
    require_any_permission,
)
from services.mail_client import build_domain_mail_client_settings
from services.mailbox_import import preview_mailbox_import
from services.mailbox_provision import provision_mailbox
from services.mxroute import mx_request, audited_mx, audit

emails_bp = Blueprint("emails", __name__)


def _mailbox_address(username, domain):
    return f"{username}@{domain}".lower()


@emails_bp.route("/api/domains/<domain>/mail-client-settings", methods=["GET"])
@require_any_permission("dashboard", "emails")
def get_mail_client_settings(domain):
    return jsonify({"success": True, "data": build_domain_mail_client_settings(domain)})


@emails_bp.route("/api/domains/<domain>/email-accounts", methods=["GET"])
@emails_bp.route("/list-emails/<domain>", methods=["GET"])  # backward compat
@require_any_permission("dashboard", "emails")
def list_emails(domain):
    result, status = mx_request("GET", f"/domains/{domain}/email-accounts")
    if status != 200:
        return result, status

    payload = result.get_json()
    if payload.get("success") and isinstance(payload.get("data"), list):
        addresses = [
            _mailbox_address(account.get("username"), domain)
            for account in payload["data"]
        ]
        recovery_map = get_recovery_map(addresses)
        for account in payload["data"]:
            username = account.get("username")
            if not username:
                continue
            mailbox_email = _mailbox_address(username, domain)
            recovery = recovery_map.get(mailbox_email)
            account["recovery_email"] = recovery
            account["has_recovery_email"] = bool(recovery)
    return jsonify(payload), status


@emails_bp.route("/api/domains/<domain>/email-accounts", methods=["POST"])
@require_permission("emails")
def create_email_api(domain):
    data = request.json or {}
    result = provision_mailbox(domain, data)
    if result.get("ok"):
        return jsonify({"success": True}), result.get("status", 201)
    return jsonify({"success": False, "error": {"message": result.get("message")}}), result.get(
        "status", 400
    )


@emails_bp.route("/api/email-accounts/import/preview", methods=["POST"])
def preview_mailbox_import_api():
    user = get_current_user()
    if not user:
        return jsonify(
            {"success": False, "error": {"message": "Unauthorized"}}
        ), 401

    data = request.json or {}
    rows = data.get("rows") or []
    default_domain = str(data.get("default_domain") or "").strip().lower()
    existing_by_domain = data.get("existing_by_domain")
    preview = preview_mailbox_import(
        rows,
        user=user,
        default_domain=default_domain,
        existing_by_domain=existing_by_domain,
    )
    if not preview.get("ok"):
        return jsonify(
            {"success": False, "error": {"message": preview.get("message")}}
        ), preview.get("status", 400)
    return jsonify({"success": True, "data": preview["data"]})


@emails_bp.route("/api/domains/<domain>/email-accounts/<user>", methods=["GET"])
@require_permission("emails")
def get_email_account(domain, user):
    return mx_request("GET", f"/domains/{domain}/email-accounts/{user}")


@emails_bp.route("/api/domains/<domain>/email-accounts/<user>", methods=["PATCH"])
@require_permission("emails")
def update_email_account(domain, user):
    if not validate_username(user):
        return jsonify(
            {"success": False, "error": {"message": "Invalid mailbox username format"}}
        ), 400
    payload = request.json or {}
    if "password" in payload:
        action = "mailbox.password_update"
    elif "quota" in payload or "limit" in payload:
        action = "mailbox.quota_update"
    else:
        action = "mailbox.update"
    return audited_mx(
        "PATCH",
        f"/domains/{domain}/email-accounts/{user}",
        payload,
        action,
        target=f"{user}@{domain}",
    )


@emails_bp.route("/api/domains/<domain>/email-accounts/<user>", methods=["DELETE"])
@require_permission("emails")
def delete_email_api(domain, user):
    if not validate_username(user):
        return jsonify(
            {"success": False, "error": {"message": "Invalid mailbox username format"}}
        ), 400
    response, status = audited_mx(
        "DELETE",
        f"/domains/{domain}/email-accounts/{user}",
        None,
        "mailbox.delete",
        target=f"{user}@{domain}",
    )
    return _delete_recovery_after_mx_delete(response, status, user, domain)


@emails_bp.route(
    "/api/domains/<domain>/email-accounts/<user>/recovery", methods=["PATCH"]
)
@require_permission("emails")
def update_recovery_email(domain, user):
    if not validate_username(user):
        return jsonify(
            {"success": False, "error": {"message": "Invalid mailbox username format"}}
        ), 400

    data = request.json or {}
    mailbox_email = _mailbox_address(user, domain)

    if "recovery_email" not in data or data.get("recovery_email") in (None, ""):
        delete_recovery_email(mailbox_email)
        audit("mailbox.recovery_update", target=mailbox_email, recovery_email=None)
        return jsonify({"success": True})

    recovery_email = str(data.get("recovery_email")).strip().lower()
    ok, message = validate_recovery_email(mailbox_email, recovery_email)
    if not ok:
        return jsonify({"success": False, "error": {"message": message}}), 400

    set_recovery_email(mailbox_email, recovery_email)
    audit(
        "mailbox.recovery_update", target=mailbox_email, recovery_email=recovery_email
    )
    return jsonify({"success": True, "data": {"recovery_email": recovery_email}})


def _delete_recovery_after_mx_delete(response, status, username, domain):
    if status in (200, 201, 204):
        payload = response.get_json()
        if payload.get("success", True):
            delete_recovery_email(_mailbox_address(username, domain))
    return response, status


@emails_bp.route("/api/domains/<domain>/forwarders", methods=["GET"])
@require_permission("forwarders")
def list_forwarders(domain):
    return mx_request("GET", f"/domains/{domain}/forwarders")


@emails_bp.route("/api/domains/<domain>/forwarders", methods=["POST"])
@require_permission("forwarders")
def create_forwarder(domain):
    data = request.json or {}
    alias = data.get("alias", "")
    return audited_mx(
        "POST",
        f"/domains/{domain}/forwarders",
        request.json,
        "forwarder.create",
        target=f"{alias}@{domain}",
    )


@emails_bp.route("/api/domains/<domain>/forwarders/<alias>", methods=["DELETE"])
@require_permission("forwarders")
def delete_forwarder(domain, alias):
    return audited_mx(
        "DELETE",
        f"/domains/{domain}/forwarders/{alias}",
        None,
        "forwarder.delete",
        target=f"{alias}@{domain}",
    )


@emails_bp.route("/api/domains/<domain>/catch-all", methods=["GET"])
@require_permission("forwarders")
def get_catch_all(domain):
    return mx_request("GET", f"/domains/{domain}/catch-all")


@emails_bp.route("/api/domains/<domain>/catch-all", methods=["PATCH"])
@require_permission("forwarders")
def update_catch_all(domain):
    return audited_mx(
        "PATCH",
        f"/domains/{domain}/catch-all",
        request.json,
        "catchall.update",
        target=domain,
    )
