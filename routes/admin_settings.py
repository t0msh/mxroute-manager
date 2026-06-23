import os

from flask import current_app, jsonify, request

from models.db import (
    SETTINGS_UI_KEYS,
    get_admin_user,
    get_conn,
    get_user_contact_email,
    invalidate_settings_cache,
    mask_settings_for_response,
    migrate_settings_secrets,
    resolve_notification_email,
    set_admin_password_hash,
)
from routes.admin_blueprint import admin_bp
from services.mail import (
    is_smtp_configured,
    send_test_email,
    smtp_config_from_overrides,
)
from services.mxroute import audit, mx_request
from utils.auth_helpers import clear_oidc_config_cache, get_current_user, require_admin
from utils.audit_log import (
    list_available_log_dates,
    normalize_log_limit,
    read_recent_log_entries,
    resolve_log_file,
)


@admin_bp.route("/api/admin/settings", methods=["GET"])
@require_admin
def get_settings():
    return jsonify({"success": True, "data": mask_settings_for_response()})


@admin_bp.route("/api/admin/settings", methods=["POST"])
@require_admin
def update_settings():
    data = request.json or {}
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            updated_keys = []

            for key in SETTINGS_UI_KEYS:
                if key in data:
                    val = str(data[key]).strip()
                    cursor.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                        (key, val),
                    )
                    updated_keys.append(key)

            conn.commit()

            if "ADMIN_PASSWORD" in data:
                new_password = str(data["ADMIN_PASSWORD"])
                if new_password.strip():
                    admin_email = (
                        str(data.get("ADMIN_USER", get_admin_user())).strip().lower()
                    )
                    set_admin_password_hash(
                        new_password.strip(), admin_email=admin_email
                    )
                    updated_keys.append("ADMIN_PASSWORD")

            migrate_settings_secrets(cursor)
            conn.commit()

        invalidate_settings_cache()
        clear_oidc_config_cache()

        if "ADMIN_PASSWORD" in updated_keys:
            audit("settings.admin_password_update", target="system")
        audit("settings.update", target="system", keys=updated_keys)
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Error saving system settings: {e}")
        return jsonify(
            {"success": False, "error": {"message": "Failed to save settings."}}
        ), 500


@admin_bp.route("/api/admin/settings/test-smtp", methods=["POST"])
@require_admin
def test_smtp_settings():
    current_user = get_current_user()
    login_identifier = (current_user or {}).get("email", "").strip().lower()
    contact_email = get_user_contact_email(login_identifier)
    recipient = resolve_notification_email(login_identifier, contact_email)

    if not recipient:
        return jsonify(
            {
                "success": False,
                "error": {
                    "message": (
                        "No deliverable email address for your account. "
                        "Add a contact email in Access Control or use an email-based login."
                    ),
                },
            }
        ), 400

    data = request.json or {}
    smtp_config = smtp_config_from_overrides(data)
    if not is_smtp_configured(smtp_config):
        return jsonify(
            {
                "success": False,
                "error": {
                    "message": "SMTP is not fully configured. Check host, user, from address, and password."
                },
            }
        ), 400

    try:
        send_test_email(recipient, smtp_config=smtp_config)
        audit("settings.smtp_test", target=login_identifier, recipient=recipient)
        return jsonify(
            {
                "success": True,
                "message": f"Test email sent to {recipient}.",
            }
        )
    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": {"message": f"Failed to send test email: {exc}"},
            }
        ), 500


@admin_bp.route("/api/quota", methods=["GET"])
@require_admin
def get_quota():
    return mx_request("GET", "/quota")


@admin_bp.route("/api/quota/email", methods=["GET"])
@require_admin
def get_quota_email():
    return mx_request("GET", "/quota/email")


@admin_bp.route("/api/admin/logs", methods=["GET"])
@require_admin
def get_logs():
    limit = normalize_log_limit(request.args.get("limit", 100))
    available_dates = list_available_log_dates()
    if not available_dates:
        return jsonify(
            {
                "success": True,
                "data": {"entries": [], "current_date": "", "available_dates": []},
            }
        )

    date_str = request.args.get("date")
    try:
        log_file, current_date = resolve_log_file(date_str or None)
    except ValueError as exc:
        return jsonify({"success": False, "error": {"message": str(exc)}}), 400

    if not log_file or not os.path.exists(log_file):
        return jsonify(
            {
                "success": True,
                "data": {
                    "entries": [],
                    "current_date": current_date,
                    "available_dates": available_dates,
                },
            }
        )

    try:
        entries = read_recent_log_entries(log_file, limit)
    except Exception as e:
        current_app.logger.error(f"Failed to read logs from {log_file}: {e}")
        return jsonify(
            {"success": False, "error": {"message": f"Failed to read logs: {e}"}}
        ), 500

    return jsonify(
        {
            "success": True,
            "data": {
                "entries": entries,
                "current_date": current_date,
                "available_dates": available_dates,
            },
        }
    )
