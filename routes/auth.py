import secrets
import sqlite3
import requests
from urllib.parse import urlencode
from werkzeug.security import check_password_hash
from flask import Blueprint, request, session, redirect, url_for, render_template, jsonify, current_app

from models.db import (
    DATABASE_FILE,
    get_admin_user,
    verify_admin_password,
    is_oidc_enabled,
    get_oidc_client_id,
    get_oidc_client_secret,
    get_oidc_redirect_uri,
    get_oidc_scopes,
    get_oidc_admin_users,
    get_oidc_admin_group,
    load_domain_mapping,
    load_user_grants,
    ALL_PERMISSIONS,
)
from utils.auth_helpers import get_oidc_config, get_current_user
from utils.audit_log import write_audit_log

auth_bp = Blueprint("auth", __name__)


def build_session_user(email, is_admin=False):
    email = email.lower()
    mapping = load_domain_mapping()
    delegated_domains = mapping.get(email, [])
    domain_grants = load_user_grants().get(email, {})
    resolved_admin = bool(
        is_admin
        or email in get_oidc_admin_users()
        or email == get_admin_user()
        or email == "admin@local"
        or "*" in delegated_domains
    )
    return {
        "email": email,
        "is_admin": resolved_admin,
        "delegated_domains": delegated_domains,
        "domain_grants": domain_grants,
    }


@auth_bp.route('/login', methods=['GET', 'POST'])
def login_page():
    if session.get("user"):
        return redirect(url_for('home'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')

        # Check SQLite database first
        user_row = None
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT id, email, password_hash, is_admin FROM users WHERE email = ?", (username,))
            user_row = cursor.fetchone()
            conn.close()
        except Exception as e:
            current_app.logger.error(f"Error checking user in SQLite: {e}")

        if user_row and user_row[2]:  # password_hash exists
            if check_password_hash(user_row[2], password):
                session["user"] = build_session_user(user_row[1], bool(user_row[3]))
                write_audit_log("auth.login", user_row[1], user_row[1])
                return redirect(url_for('home'))

        # Fallback to local admin config check (hashed password only)
        if username == get_admin_user() and verify_admin_password(password):
            session["user"] = build_session_user(username, True)
            write_audit_log("auth.login", username, username)
            return redirect(url_for('home'))

        write_audit_log("auth.login_failed", username, username, {"reason": "invalid_credentials"})
        error = "Invalid credentials. Please try again."

    return render_template('login.html', error=error)


@auth_bp.route('/login/redirect')
def login_redirect():
    if not is_oidc_enabled():
        return redirect(url_for('home'))
    try:
        config = get_oidc_config()
    except Exception as e:
        return f"Error: OIDC provider configuration failed: {e}", 500

    auth_endpoint = config.get("authorization_endpoint")
    if not auth_endpoint:
        return "Error: OIDC provider configuration does not define authorization_endpoint", 500

    # Prevent CSRF
    state = secrets.token_urlsafe(16)
    session["oidc_state"] = state

    params = {
        "client_id": get_oidc_client_id(),
        "response_type": "code",
        "scope": get_oidc_scopes(),
        "redirect_uri": get_oidc_redirect_uri(),
        "state": state
    }

    auth_url = f"{auth_endpoint}?{urlencode(params)}"
    return redirect(auth_url)


@auth_bp.route('/oidc/callback')
def oidc_callback():
    if not is_oidc_enabled():
        return redirect(url_for('home'))

    state = request.args.get('state')
    expected_state = session.pop("oidc_state", None)
    if not state or not expected_state or not secrets.compare_digest(state, expected_state):
        return "Authentication error: CSRF state verification failed", 400

    code = request.args.get('code')
    if not code:
        return "Authentication error: Missing authorization code", 400

    try:
        config = get_oidc_config()
        token_endpoint = config.get("token_endpoint")
        userinfo_endpoint = config.get("userinfo_endpoint")

        if not token_endpoint:
            return "Error: OIDC token endpoint not configured", 500

        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": get_oidc_redirect_uri(),
            "client_id": get_oidc_client_id(),
            "client_secret": get_oidc_client_secret()
        }
        token_res = requests.post(token_endpoint, data=payload, timeout=15)
        token_res.raise_for_status()
        token_data = token_res.json()

        access_token = token_data.get("access_token")
        if not access_token:
            return "Error: OIDC token response did not contain access_token", 500

        if not userinfo_endpoint:
            return "Error: OIDC userinfo endpoint not configured", 500

        userinfo_res = requests.get(userinfo_endpoint, headers={
            "Authorization": f"Bearer {access_token}"
        }, timeout=15)
        userinfo_res.raise_for_status()
        userinfo_data = userinfo_res.json()

        email = userinfo_data.get("email") or userinfo_data.get("sub") or userinfo_data.get("preferred_username")
        if not email:
            return "Error: User identification claim not found in userinfo", 500

        email = email.lower().strip()

        # Check if user is an admin by email OR by OIDC group membership
        user_groups = userinfo_data.get("groups", [])
        if not isinstance(user_groups, list):
            user_groups = []
        is_admin = (email in get_oidc_admin_users()) or (get_oidc_admin_group() in user_groups)

        user_row = None
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()

            cursor.execute("SELECT id, is_admin FROM users WHERE email = ?", (email,))
            user_row = cursor.fetchone()

            if is_admin:
                if not user_row:
                    cursor.execute(
                        "INSERT INTO users (email, is_admin) VALUES (?, 1)",
                        (email,)
                    )
                else:
                    cursor.execute(
                        "UPDATE users SET is_admin = 1 WHERE email = ?",
                        (email,)
                    )
                conn.commit()
            else:
                # If they are not an administrator, check if they exist in the database (delegated user)
                if not user_row:
                    conn.close()
                    return render_template('login.html', error="You do not have access to this tool. Please contact an administrator.")

            conn.close()
        except Exception as db_err:
            current_app.logger.error(f"Failed to query/insert OIDC user in database: {db_err}")

        session["user"] = build_session_user(
            email,
            is_admin or (user_row and bool(user_row[1])),
        )

        write_audit_log("auth.login", email, email, {"method": "oidc"})
        return redirect(url_for('home'))
    except Exception as e:
        current_app.logger.error(f"OIDC flow callback failure: {e}")
        return f"Authentication failed: {e}", 500


@auth_bp.route('/logout')
def logout():
    user = get_current_user()
    if user:
        email = user.get("email", "unknown")
        write_audit_log("auth.logout", email, email)
    session.pop('user', None)
    return redirect(url_for('auth.login_page'))


@auth_bp.route('/api/me')
def get_me():
    user = get_current_user()
    if user:
        email = user.get("email")
        if isinstance(email, str):
            is_admin = False
            try:
                conn = sqlite3.connect(DATABASE_FILE)
                cursor = conn.cursor()
                cursor.execute("SELECT is_admin FROM users WHERE email = ?", (email.lower(),))
                row = cursor.fetchone()
                if row:
                    is_admin = bool(row[0])
                conn.close()
            except Exception:
                pass

            user = build_session_user(email, is_admin)
            session["user"] = user

    return jsonify({
        "success": True,
        "oidc_enabled": is_oidc_enabled(),
        "permissions": list(ALL_PERMISSIONS),
        "user": {
            "email": user.get("email"),
            "is_admin": user.get("is_admin", False),
            "delegated_domains": user.get("delegated_domains", []),
            "domain_grants": user.get("domain_grants", {}),
        } if user else None
    })
