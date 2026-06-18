import json
import sqlite3
from flask import Blueprint, request, jsonify

from models.db import (
    DATABASE_FILE,
    SETTINGS_UI_KEYS,
    set_admin_password_hash,
    set_reset_smtp_password,
    get_admin_user,
    migrate_settings_secrets,
    mask_settings_for_response,
    load_delegations_detail,
    is_oidc_enabled,
    invalidate_settings_cache,
    ALL_PERMISSIONS,
    DEFAULT_PERMISSIONS,
    _normalize_permissions,
    resolve_notification_email,
    get_user_contact_email,
)
from werkzeug.security import generate_password_hash
from utils.auth_helpers import require_admin, get_current_user, clear_oidc_config_cache
from utils.validators import validate_local_user_identifier, requires_local_password, is_email_identifier
from services.mxroute import mx_request, audit
from services.mail import send_test_email, smtp_config_from_overrides, is_smtp_configured

admin_bp = Blueprint("admin", __name__)


# --- DELEGATIONS ACCESS CONTROL API (ADMIN ONLY) ---

@admin_bp.route('/api/admin/delegations', methods=['GET'])
@require_admin
def list_delegations():
    return jsonify({
        "success": True,
        "data": load_delegations_detail(),
        "permissions": list(ALL_PERMISSIONS),
    })


def _parse_delegation_grants(data):
    grants = data.get("grants")
    if isinstance(grants, list):
        parsed = []
        for grant in grants:
            if not isinstance(grant, dict):
                continue
            domain = (grant.get("domain") or "").strip().lower()
            if not domain or domain == "*":
                continue
            permissions = _normalize_permissions(grant.get("permissions"))
            parsed.append({"domain": domain, "permissions": permissions})
        return parsed

    domains = data.get("domains")
    if isinstance(domains, list):
        return [
            {"domain": d.strip().lower(), "permissions": list(DEFAULT_PERMISSIONS)}
            for d in domains
            if isinstance(d, str) and d.strip() and d.strip().lower() != "*"
        ]
    return []


@admin_bp.route('/api/admin/delegations', methods=['POST'])
@require_admin
def update_delegation():
    data = request.json or {}
    email = data.get("email")
    password = data.get("password")

    if not email:
        return jsonify({"success": False, "error": {"message": "User identifier is required"}}), 400

    email = email.strip().lower()
    if not validate_local_user_identifier(email):
        return jsonify({
            "success": False,
            "error": {"message": "Invalid user identifier. Use a username (e.g. billy), user@local, or email address."},
        }), 400

    grants = _parse_delegation_grants(data)
    domains = data.get("domains")
    is_admin = False
    if isinstance(domains, list):
        is_admin = "*" in [d.strip().lower() for d in domains if isinstance(d, str)]
    if not is_admin and not grants:
        return jsonify({
            "success": False,
            "error": {"message": "Select at least one domain with permissions, or grant Admin access."},
        }), 400

    for grant in grants:
        if not grant["permissions"]:
            return jsonify({
                "success": False,
                "error": {"message": f"Select at least one permission for {grant['domain']}."},
            }), 400

    local_user = requires_local_password(email, is_oidc_enabled())
    password_provided = bool(password and str(password).strip())

    contact_email = None
    update_contact_email = "contact_email" in data
    if update_contact_email:
        contact_email = str(data.get("contact_email") or "").strip().lower() or None
        if contact_email and not is_email_identifier(contact_email):
            return jsonify({
                "success": False,
                "error": {"message": "Invalid contact email format."},
            }), 400

    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        cursor.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()

        if not row:
            if local_user and not password_provided:
                conn.close()
                return jsonify({
                    "success": False,
                    "error": {"message": "Password is required when creating a local user."},
                }), 400
        elif local_user and not row[1] and not password_provided:
            conn.close()
            return jsonify({
                "success": False,
                "error": {"message": "Password is required for local users who do not have one set."},
            }), 400

        hashed_password = generate_password_hash(password) if password_provided else None

        if not row:
            cursor.execute(
                "INSERT INTO users (email, password_hash, is_admin, contact_email) VALUES (?, ?, ?, ?)",
                (email, hashed_password, 1 if is_admin else 0, contact_email if update_contact_email else None)
            )
            user_id = cursor.lastrowid
        else:
            user_id = row[0]
            if password_provided and update_contact_email:
                cursor.execute(
                    "UPDATE users SET password_hash = ?, is_admin = ?, contact_email = ? WHERE id = ?",
                    (hashed_password, 1 if is_admin else 0, contact_email, user_id)
                )
            elif password_provided:
                cursor.execute(
                    "UPDATE users SET password_hash = ?, is_admin = ? WHERE id = ?",
                    (hashed_password, 1 if is_admin else 0, user_id)
                )
            elif update_contact_email:
                cursor.execute(
                    "UPDATE users SET is_admin = ?, contact_email = ? WHERE id = ?",
                    (1 if is_admin else 0, contact_email, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE users SET is_admin = ? WHERE id = ?",
                    (1 if is_admin else 0, user_id)
                )

        cursor.execute("DELETE FROM delegations WHERE user_id = ?", (user_id,))
        if not is_admin:
            for grant in grants:
                cursor.execute(
                    "INSERT INTO delegations (user_id, domain, permissions) VALUES (?, ?, ?)",
                    (user_id, grant["domain"], json.dumps(grant["permissions"])),
                )

        conn.commit()
        conn.close()
        audit(
            "delegation.update",
            target=email,
            domains=[grant["domain"] for grant in grants],
            is_admin=is_admin,
            grants=grants,
        )
        return jsonify({"success": True})
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error updating user delegations in SQLite: {e}")
        return jsonify({"success": False, "error": {"message": f"Failed to save configuration: {e}"}}), 500


@admin_bp.route('/api/admin/delegations', methods=['DELETE'])
@admin_bp.route('/api/admin/delegations/<path:email>', methods=['DELETE'])
@require_admin
def delete_delegation(email=None):
    if not email:
        email = request.args.get("email")
    if not email and request.is_json:
        body = request.get_json(silent=True) or {}
        email = body.get("email")

    if not email:
        return jsonify({"success": False, "error": {"message": "User identifier is required"}}), 400

    email = email.strip().lower()
    if not validate_local_user_identifier(email):
        return jsonify({
            "success": False,
            "error": {"message": "Invalid user identifier. Use a username (e.g. billy), user@local, or email address."},
        }), 400

    current_user = get_current_user()
    if current_user and current_user.get("email", "").lower() == email:
        return jsonify({"success": False, "error": {"message": "Conflict: You cannot revoke/delete your own account."}}), 409

    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        # Delete user delegations & user record
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if row:
            user_id = row[0]
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            cursor.execute("DELETE FROM delegations WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            audit("delegation.revoke", target=email)
            return jsonify({"success": True})
        return jsonify({"success": False, "error": {"message": "User not found"}}), 404
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error deleting user delegations from SQLite: {e}")
        return jsonify({"success": False, "error": {"message": f"Failed to delete configuration: {e}"}}), 500


# --- SYSTEM SETTINGS API (ADMIN ONLY) ---

@admin_bp.route('/api/admin/settings', methods=['GET'])
@require_admin
def get_settings():
    return jsonify({
        "success": True,
        "data": mask_settings_for_response()
    })


@admin_bp.route('/api/admin/settings', methods=['POST'])
@require_admin
def update_settings():
    data = request.json or {}
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        updated_keys = []

        for key in SETTINGS_UI_KEYS:
            if key in data:
                val = str(data[key]).strip()
                cursor.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, val)
                )
                updated_keys.append(key)

        conn.commit()

        if "ADMIN_PASSWORD" in data:
            new_password = str(data["ADMIN_PASSWORD"])
            if new_password.strip():
                admin_email = str(data.get("ADMIN_USER", get_admin_user())).strip().lower()
                set_admin_password_hash(new_password.strip(), admin_email=admin_email)
                updated_keys.append("ADMIN_PASSWORD")

        if "RESET_SMTP_PASSWORD" in data:
            new_smtp_password = str(data["RESET_SMTP_PASSWORD"])
            if new_smtp_password.strip():
                set_reset_smtp_password(new_smtp_password.strip())
                updated_keys.append("RESET_SMTP_PASSWORD")

        migrate_settings_secrets(cursor)
        conn.commit()
        conn.close()

        # Clear cached settings + OIDC config so changes take effect immediately
        invalidate_settings_cache()
        clear_oidc_config_cache()

        audit("settings.update", target="system", keys=updated_keys)
        return jsonify({"success": True})
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error saving system settings: {e}")
        return jsonify({"success": False, "error": {"message": f"Failed to save settings: {e}"}}), 500


@admin_bp.route('/api/admin/settings/test-smtp', methods=['POST'])
@require_admin
def test_smtp_settings():
    current_user = get_current_user()
    login_identifier = (current_user or {}).get("email", "").strip().lower()
    contact_email = get_user_contact_email(login_identifier)
    recipient = resolve_notification_email(login_identifier, contact_email)

    if not recipient:
        return jsonify({
            "success": False,
            "error": {
                "message": (
                    "No deliverable email address for your account. "
                    "Add a contact email in Access Control or use an email-based login."
                ),
            },
        }), 400

    data = request.json or {}
    smtp_config = smtp_config_from_overrides(data)
    if not is_smtp_configured(smtp_config):
        return jsonify({
            "success": False,
            "error": {"message": "SMTP is not fully configured. Check host, user, from address, and password."},
        }), 400

    try:
        send_test_email(recipient, smtp_config=smtp_config)
        audit("settings.smtp_test", target=login_identifier, recipient=recipient)
        return jsonify({
            "success": True,
            "message": f"Test email sent to {recipient}.",
        })
    except Exception as exc:
        return jsonify({
            "success": False,
            "error": {"message": f"Failed to send test email: {exc}"},
        }), 500


# --- QUOTA ---

@admin_bp.route('/api/quota', methods=['GET'])
@require_admin
def get_quota():
    return mx_request("GET", "/quota")


@admin_bp.route('/api/quota/email', methods=['GET'])
@require_admin
def get_quota_email():
    return mx_request("GET", "/quota/email")


@admin_bp.route('/api/admin/logs', methods=['GET'])
@require_admin
def get_logs():
    import os
    from utils.audit_log import (
        list_available_log_dates,
        normalize_log_limit,
        read_recent_log_entries,
        resolve_log_file,
    )

    limit = normalize_log_limit(request.args.get("limit", 100))
    available_dates = list_available_log_dates()
    if not available_dates:
        return jsonify({"success": True, "data": {"entries": [], "current_date": "", "available_dates": []}})

    date_str = request.args.get("date")
    try:
        log_file, current_date = resolve_log_file(date_str or None)
    except ValueError as exc:
        return jsonify({"success": False, "error": {"message": str(exc)}}), 400

    if not log_file or not os.path.exists(log_file):
        return jsonify({
            "success": True,
            "data": {
                "entries": [],
                "current_date": current_date,
                "available_dates": available_dates,
            },
        })

    try:
        entries = read_recent_log_entries(log_file, limit)
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Failed to read logs from {log_file}: {e}")
        return jsonify({"success": False, "error": {"message": f"Failed to read logs: {e}"}}), 500

    return jsonify({
        "success": True,
        "data": {
            "entries": entries,
            "current_date": current_date,
            "available_dates": available_dates,
        },
    })

