"""Shared mailbox creation (single and bulk import)."""

from models.db import set_recovery_email
from services.mxroute import audited_mx, audit
from utils.validators import (
    validate_mailbox_password,
    validate_recovery_email,
    validate_username,
)

DEFAULT_QUOTA = 1024
DEFAULT_LIMIT = 9600
MAX_IMPORT_ROWS = 250


def _mailbox_address(username, domain):
    return f"{username}@{domain}".lower()


def _mx_payload_without_recovery(data):
    if not isinstance(data, dict):
        return data
    return {key: value for key, value in data.items() if key != "recovery_email"}


def provision_mailbox(domain, payload):
    """Create a mailbox on MXroute and optional recovery email.

    Returns ``{"ok": True, "status": 201}`` or ``{"ok": False, "status": int, "message": str}``.
    """
    if not isinstance(payload, dict):
        return {"ok": False, "status": 400, "message": "Invalid payload"}

    username = str(payload.get("username") or "").strip().lower()
    password = payload.get("password")
    if not validate_username(username):
        return {
            "ok": False,
            "status": 400,
            "message": "Invalid mailbox username format",
        }
    if not validate_mailbox_password(password):
        return {
            "ok": False,
            "status": 400,
            "message": "Password does not meet requirements",
        }

    recovery_email = (payload.get("recovery_email") or "").strip().lower() or None
    mailbox_email = _mailbox_address(username, domain)
    if recovery_email:
        ok, message = validate_recovery_email(mailbox_email, recovery_email)
        if not ok:
            return {"ok": False, "status": 400, "message": message}

    mx_payload = _mx_payload_without_recovery(payload)
    mx_payload["username"] = username

    response, status = audited_mx(
        "POST",
        f"/domains/{domain}/email-accounts",
        mx_payload,
        "mailbox.create",
        target=mailbox_email,
    )
    body = response.get_json() if hasattr(response, "get_json") else {}
    if status in (200, 201, 204) and body.get("success", True):
        if recovery_email:
            set_recovery_email(mailbox_email, recovery_email)
            audit(
                "mailbox.recovery_update",
                target=mailbox_email,
                recovery_email=recovery_email,
            )
        return {"ok": True, "status": status, "mailbox": mailbox_email}

    message = "Failed to create mailbox"
    if isinstance(body, dict):
        err = body.get("error") or {}
        if isinstance(err, dict) and err.get("message"):
            message = err["message"]
    return {"ok": False, "status": status, "message": message}
