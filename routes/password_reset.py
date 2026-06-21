import time
from collections import defaultdict
from threading import Lock

from flask import Blueprint, request, jsonify, render_template, url_for, g

from models.db import (
    create_reset_token,
    consume_reset_token,
    get_recovery_email,
    get_active_reset_portal_for_mailbox_domain,
    is_mailbox_reset_enabled,
    parse_mailbox_email,
    build_reset_portal_url,
)
from services.mail import is_password_reset_available, is_smtp_configured, send_password_reset_email
from services.mxroute import mx_request_raw
from services.reset_portal import get_portal_branding_context
from services.reset_portal_mail import build_portal_reset_from_address
from utils.audit_log import write_audit_log
from utils.validators import is_email_identifier, validate_mailbox_password

password_reset_bp = Blueprint("password_reset", __name__)

GENERIC_SUCCESS = (
    "If an account with a recovery email on file exists, "
    "you will receive password reset instructions shortly."
)

_RATE_LOCK = Lock()
_RATE_BUCKETS = defaultdict(list)
_IP_LIMIT = 5
_MAILBOX_LIMIT = 3
_WINDOW_SECONDS = 3600


def _client_ip():
    # request.remote_addr is set from X-Forwarded-For by ProxyFix using the
    # configured trusted-proxy hop count, so it cannot be spoofed by clients.
    return request.remote_addr or "unknown"


def _rate_limit_ok(bucket_key, limit):
    now = time.time()
    with _RATE_LOCK:
        timestamps = _RATE_BUCKETS[bucket_key]
        timestamps[:] = [ts for ts in timestamps if now - ts < _WINDOW_SECONDS]
        if len(timestamps) >= limit:
            return False
        timestamps.append(now)
        return True


def _audit_public(action, target="", **details):
    write_audit_log(action, "public", target, details or None)


def _mailbox_allowed_for_portal(mailbox_domain):
    portal_domain = getattr(g, "reset_portal_domain", None)
    if not portal_domain:
        return True
    return mailbox_domain == portal_domain


@password_reset_bp.route("/api/public/password-reset/status", methods=["GET"])
def password_reset_status():
    return jsonify({
        "success": True,
        "data": {
            "enabled": is_mailbox_reset_enabled(),
            "configured": is_smtp_configured(),
            "available": is_password_reset_available(),
        },
    })


@password_reset_bp.route("/api/public/password-reset/request", methods=["POST"])
def password_reset_request():
    if not is_password_reset_available():
        return jsonify({"success": True, "message": GENERIC_SUCCESS})

    data = request.json or {}
    mailbox_email = (data.get("mailbox_email") or "").strip().lower()

    if not is_email_identifier(mailbox_email):
        return jsonify({"success": True, "message": GENERIC_SUCCESS})

    username, domain = parse_mailbox_email(mailbox_email)
    if not username:
        return jsonify({"success": True, "message": GENERIC_SUCCESS})

    if not _mailbox_allowed_for_portal(domain):
        return jsonify({"success": True, "message": GENERIC_SUCCESS})

    client_ip = _client_ip()
    if not _rate_limit_ok(f"ip:{client_ip}", _IP_LIMIT):
        return jsonify({"success": True, "message": GENERIC_SUCCESS})
    if not _rate_limit_ok(f"mailbox:{mailbox_email}", _MAILBOX_LIMIT):
        return jsonify({"success": True, "message": GENERIC_SUCCESS})

    recovery_email = get_recovery_email(mailbox_email)
    if not recovery_email:
        return jsonify({"success": True, "message": GENERIC_SUCCESS})

    raw_token = create_reset_token(mailbox_email)
    reset_url = build_reset_portal_url(domain, raw_token)
    if not reset_url:
        reset_url = url_for(
            "password_reset.reset_password_page",
            token=raw_token,
            _external=True,
        )

    try:
        portal = get_active_reset_portal_for_mailbox_domain(domain)
        from_address = build_portal_reset_from_address(portal, domain) if portal else None
        send_password_reset_email(
            recovery_email,
            mailbox_email,
            reset_url,
            from_address=from_address,
        )
        _audit_public("mailbox.reset_requested", target=mailbox_email)
    except Exception:
        pass

    return jsonify({"success": True, "message": GENERIC_SUCCESS})


@password_reset_bp.route("/reset-password", methods=["GET"])
def reset_password_page():
    token = (request.args.get("token") or "").strip()
    branding = get_portal_branding_context(getattr(g, "reset_portal", None))
    return render_template(
        "reset_password.html",
        token=token,
        reset_available=is_password_reset_available(),
        **branding,
    )


@password_reset_bp.route("/api/public/password-reset/confirm", methods=["POST"])
def password_reset_confirm():
    if not is_password_reset_available():
        return jsonify({
            "success": False,
            "error": {"message": "Password reset is not available."},
        }), 503

    data = request.json or {}
    raw_token = (data.get("token") or "").strip()
    password = data.get("password") or ""

    if not raw_token:
        return jsonify({
            "success": False,
            "error": {"message": "Invalid or expired reset link."},
        }), 400

    if not validate_mailbox_password(password):
        return jsonify({
            "success": False,
            "error": {"message": "Password does not meet requirements."},
        }), 400

    mailbox_email = consume_reset_token(raw_token)
    if not mailbox_email:
        return jsonify({
            "success": False,
            "error": {"message": "Invalid or expired reset link."},
        }), 400

    username, domain = parse_mailbox_email(mailbox_email)
    if not username:
        return jsonify({
            "success": False,
            "error": {"message": "Invalid or expired reset link."},
        }), 400

    if not _mailbox_allowed_for_portal(domain):
        return jsonify({
            "success": False,
            "error": {"message": "Invalid or expired reset link."},
        }), 400

    res, status = mx_request_raw(
        "PATCH",
        f"/domains/{domain}/email-accounts/{username}",
        {"password": password},
    )
    if status not in (200, 201, 204) or (isinstance(res, dict) and not res.get("success", True)):
        message = "Failed to update mailbox password."
        if isinstance(res, dict):
            message = res.get("error", {}).get("message", message)
        return jsonify({"success": False, "error": {"message": message}}), status if status >= 400 else 500

    _audit_public("mailbox.reset_completed", target=mailbox_email)
    return jsonify({"success": True, "message": "Your mailbox password has been updated."})
