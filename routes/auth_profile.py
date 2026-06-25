from flask import session, redirect, url_for, request, jsonify, current_app

from models.db import (
    ALL_PERMISSIONS,
    get_conn,
    get_user_contact_email,
    is_oidc_enabled,
    resolve_notification_email,
    set_user_contact_email,
)
from routes.auth_blueprint import auth_bp
from routes.auth_session import build_session_user
from utils.auth_helpers import get_current_user
from utils.audit_log import write_audit_log
from utils.validators import is_email_identifier


@auth_bp.route("/logout")
def logout():
    user = get_current_user()
    if user:
        email = user.get("email", "unknown")
        write_audit_log("auth.logout", email, email)
    session.pop("user", None)
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/api/me")
def get_me():
    user = get_current_user()
    if user:
        email = user.get("email")
        if isinstance(email, str):
            is_admin = False
            try:
                with get_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT is_admin FROM users WHERE email = ?", (email.lower(),)
                    )
                    row = cursor.fetchone()
                if row:
                    is_admin = bool(row[0])
            except Exception as e:
                current_app.logger.warning(
                    f"Failed to refresh admin flag for {email}: {e}"
                )

            user = build_session_user(email, is_admin)
            session["user"] = user

    return jsonify(
        {
            "success": True,
            "oidc_enabled": is_oidc_enabled(),
            "permissions": list(ALL_PERMISSIONS),
            "user": {
                "email": user.get("email"),
                "contact_email": get_user_contact_email(user.get("email")),
                "notification_email": resolve_notification_email(user.get("email")),
                "is_admin": user.get("is_admin", False),
                "delegated_domains": user.get("delegated_domains", []),
                "domain_grants": user.get("domain_grants", {}),
            }
            if user
            else None,
        }
    )


@auth_bp.route("/api/me/profile", methods=["PATCH"])
def update_profile():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": {"message": "Unauthorized"}}), 401

    data = request.json or {}
    login_identifier = user.get("email", "").strip().lower()
    if "contact_email" not in data:
        return jsonify(
            {"success": False, "error": {"message": "No profile fields provided."}}
        ), 400

    contact_email = str(data.get("contact_email") or "").strip().lower() or None
    if contact_email and not is_email_identifier(contact_email):
        return jsonify(
            {"success": False, "error": {"message": "Invalid contact email format."}}
        ), 400

    set_user_contact_email(
        login_identifier,
        contact_email,
        is_admin=user.get("is_admin", False),
    )
    write_audit_log(
        "profile.update",
        login_identifier,
        login_identifier,
        {"contact_email": contact_email},
    )
    return jsonify(
        {
            "success": True,
            "data": {
                "contact_email": contact_email,
                "notification_email": resolve_notification_email(
                    login_identifier, contact_email
                ),
            },
        }
    )
