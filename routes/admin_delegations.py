import json

from flask import current_app, jsonify, request
from werkzeug.security import generate_password_hash

from models.db import (
    ALL_PERMISSIONS,
    DEFAULT_PERMISSIONS,
    _normalize_permissions,
    get_conn,
    is_oidc_enabled,
    load_delegations_detail,
)
from routes.admin_blueprint import admin_bp
from services.mxroute import audit
from utils.auth_helpers import get_current_user, require_admin
from utils.api_response import escape_client_text, json_error
from utils.validators import (
    is_email_identifier,
    requires_local_password,
    validate_local_user_identifier,
)

_INVALID_IDENTIFIER = "Invalid user identifier. Use a username (e.g. billy), user@local, or email address."


def _normalize_delegation_email(raw_email):
    if not raw_email:
        return None, ("User identifier is required", 400)
    email = raw_email.strip().lower()
    if not validate_local_user_identifier(email):
        return None, (_INVALID_IDENTIFIER, 400)
    return email, None


def _delegation_email_from_request(email=None):
    if not email:
        email = request.args.get("email")
    if not email and request.is_json:
        email = (request.get_json(silent=True) or {}).get("email")
    return _normalize_delegation_email(email)


def parse_delegation_grants(data):
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


def _is_admin_from_domains(data):
    domains = data.get("domains")
    if not isinstance(domains, list):
        return False
    return "*" in [d.strip().lower() for d in domains if isinstance(d, str)]


def _validate_grant_list(grants, is_admin):
    if not is_admin and not grants:
        return (
            "Select at least one domain with permissions, or grant Admin access.",
            400,
        )
    for grant in grants:
        if not grant["permissions"]:
            domain = escape_client_text(grant["domain"])
            return (f"Select at least one permission for {domain}.", 400)
    return None


def _parse_contact_email(data):
    if "contact_email" not in data:
        return None, False, None
    contact_email = str(data.get("contact_email") or "").strip().lower() or None
    if contact_email and not is_email_identifier(contact_email):
        return None, True, ("Invalid contact email format.", 400)
    return contact_email, True, None


def _password_required_error(row, local_user, password_provided):
    if not row and local_user and not password_provided:
        return ("Password is required when creating a local user.", 400)
    if row and local_user and not row[1] and not password_provided:
        return (
            "Password is required for local users who do not have one set.",
            400,
        )
    return None


def _upsert_delegation_user(cursor, update):
    email = update["email"]
    row = update["row"]
    is_admin = update["is_admin"]
    password_provided = update["password_provided"]
    password = update["password"]
    contact_email = update["contact_email"]
    update_contact_email = update["update_contact_email"]
    admin_flag = 1 if is_admin else 0
    hashed_password = generate_password_hash(password) if password_provided else None

    if not row:
        cursor.execute(
            "INSERT INTO users (email, password_hash, is_admin, contact_email) VALUES (?, ?, ?, ?)",
            (
                email,
                hashed_password,
                admin_flag,
                contact_email if update_contact_email else None,
            ),
        )
        return cursor.lastrowid

    user_id = row[0]
    if password_provided and update_contact_email:
        cursor.execute(
            "UPDATE users SET password_hash = ?, is_admin = ?, contact_email = ? WHERE id = ?",
            (hashed_password, admin_flag, contact_email, user_id),
        )
    elif password_provided:
        cursor.execute(
            "UPDATE users SET password_hash = ?, is_admin = ? WHERE id = ?",
            (hashed_password, admin_flag, user_id),
        )
    elif update_contact_email:
        cursor.execute(
            "UPDATE users SET is_admin = ?, contact_email = ? WHERE id = ?",
            (admin_flag, contact_email, user_id),
        )
    else:
        cursor.execute(
            "UPDATE users SET is_admin = ? WHERE id = ?",
            (admin_flag, user_id),
        )
    return user_id


def _replace_user_delegations(cursor, user_id, is_admin, grants):
    cursor.execute("DELETE FROM delegations WHERE user_id = ?", (user_id,))
    if is_admin:
        return
    for grant in grants:
        cursor.execute(
            "INSERT INTO delegations (user_id, domain, permissions) VALUES (?, ?, ?)",
            (user_id, grant["domain"], json.dumps(grant["permissions"])),
        )


@admin_bp.route("/api/admin/delegations", methods=["GET"])
@require_admin
def list_delegations():
    return jsonify(
        {
            "success": True,
            "data": load_delegations_detail(),
            "permissions": list(ALL_PERMISSIONS),
        }
    )


@admin_bp.route("/api/admin/delegations", methods=["POST"])
@require_admin
def update_delegation():
    data = request.json or {}
    email, err = _normalize_delegation_email(data.get("email"))
    if err:
        return json_error(*err)

    grants = parse_delegation_grants(data)
    is_admin = _is_admin_from_domains(data)
    err = _validate_grant_list(grants, is_admin)
    if err:
        return json_error(*err)

    contact_email, update_contact_email, err = _parse_contact_email(data)
    if err:
        return json_error(*err)

    password = data.get("password")
    password_provided = bool(password and str(password).strip())
    local_user = requires_local_password(email, is_oidc_enabled())

    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, password_hash FROM users WHERE email = ?", (email,)
            )
            row = cursor.fetchone()

            err = _password_required_error(row, local_user, password_provided)
            if err:
                return json_error(*err)

            user_id = _upsert_delegation_user(
                cursor,
                {
                    "email": email,
                    "row": row,
                    "is_admin": is_admin,
                    "password_provided": password_provided,
                    "password": password,
                    "contact_email": contact_email,
                    "update_contact_email": update_contact_email,
                },
            )
            _replace_user_delegations(cursor, user_id, is_admin, grants)
            conn.commit()

        audit(
            "delegation.update",
            target=email,
            domains=[grant["domain"] for grant in grants],
            is_admin=is_admin,
            grants=grants,
        )
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Error updating user delegations in SQLite: {e}")
        return json_error("Failed to save configuration.", 500)


@admin_bp.route("/api/admin/delegations", methods=["DELETE"])
@admin_bp.route("/api/admin/delegations/<path:email>", methods=["DELETE"])
@require_admin
def delete_delegation(email=None):
    email, err = _delegation_email_from_request(email)
    if err:
        return json_error(*err)

    current_user = get_current_user()
    if current_user and current_user.get("email", "").lower() == email:
        return json_error("Conflict: You cannot revoke/delete your own account.", 409)

    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()
            if not row:
                return json_error("User not found", 404)
            user_id = row[0]
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            cursor.execute("DELETE FROM delegations WHERE user_id = ?", (user_id,))
            conn.commit()
        audit("delegation.revoke", target=email)
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Error deleting user delegations from SQLite: {e}")
        return json_error("Failed to delete configuration.", 500)
