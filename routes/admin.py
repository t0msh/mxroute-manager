import sqlite3
from flask import Blueprint, request, jsonify

from models.db import (
    DATABASE_FILE,
    SETTINGS_UI_KEYS,
    set_admin_password_hash,
    get_admin_user,
    migrate_settings_secrets,
    mask_settings_for_response,
    load_domain_mapping,
)
from utils.auth_helpers import require_admin, get_current_user, clear_oidc_config_cache
from services.mxroute import mx_request, audit

admin_bp = Blueprint("admin", __name__)


# --- DELEGATIONS ACCESS CONTROL API (ADMIN ONLY) ---

@admin_bp.route('/api/admin/delegations', methods=['GET'])
@require_admin
def list_delegations():
    mapping = load_domain_mapping()
    delegations_list = []
    for email, domains in mapping.items():
        delegations_list.append({
            "email": email,
            "domains": domains
        })
    return jsonify({
        "success": True,
        "data": delegations_list
    })


@admin_bp.route('/api/admin/delegations', methods=['POST'])
@require_admin
def update_delegation():
    data = request.json or {}
    email = data.get("email")
    domains = data.get("domains")
    password = data.get("password")

    if not email:
        return jsonify({"success": False, "error": {"message": "Email is required"}}), 400
    if not isinstance(domains, list):
        return jsonify({"success": False, "error": {"message": "Domains list is required"}}), 400

    email = email.strip().lower()
    normalized_domains = [d.strip().lower() for d in domains if d.strip()]
    is_admin = "*" in normalized_domains

    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()

        from werkzeug.security import generate_password_hash
        hashed_password = generate_password_hash(password) if password else None

        if not row:
            # Create user
            cursor.execute(
                "INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, ?)",
                (email, hashed_password, 1 if is_admin else 0)
            )
            user_id = cursor.lastrowid
        else:
            user_id = row[0]
            # Update user
            if password:
                cursor.execute(
                    "UPDATE users SET password_hash = ?, is_admin = ? WHERE id = ?",
                    (hashed_password, 1 if is_admin else 0, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE users SET is_admin = ? WHERE id = ?",
                    (1 if is_admin else 0, user_id)
                )

        # Update delegations
        cursor.execute("DELETE FROM delegations WHERE user_id = ?", (user_id,))
        for d in normalized_domains:
            if d == "*":
                continue
            cursor.execute(
                "INSERT INTO delegations (user_id, domain) VALUES (?, ?)",
                (user_id, d)
            )

        conn.commit()
        conn.close()
        audit("delegation.update", target=email, domains=normalized_domains, is_admin=is_admin)
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
        return jsonify({"success": False, "error": {"message": "Email parameter is required"}}), 400

    email = email.strip().lower()

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

        migrate_settings_secrets(cursor)
        conn.commit()
        conn.close()

        # Clear the cached OIDC config
        clear_oidc_config_cache()

        audit("settings.update", target="system", keys=updated_keys)
        return jsonify({"success": True})
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Error saving system settings: {e}")
        return jsonify({"success": False, "error": {"message": f"Failed to save settings: {e}"}}), 500


# --- QUOTA ---

@admin_bp.route('/api/quota', methods=['GET'])
@require_admin
def get_quota():
    return mx_request("GET", "/quota")


@admin_bp.route('/api/quota/email', methods=['GET'])
@require_admin
def get_quota_email():
    return mx_request("GET", "/quota/email")
