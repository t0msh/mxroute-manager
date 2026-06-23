import secrets
import requests
from urllib.parse import urlencode
from werkzeug.security import check_password_hash
from flask import (
    Blueprint,
    request,
    session,
    redirect,
    url_for,
    render_template,
    jsonify,
    current_app,
)

from models.db import (
    get_conn,
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
    get_user_contact_email,
    resolve_notification_email,
    set_user_contact_email,
)
from utils.auth_helpers import get_oidc_config, get_current_user
from utils.audit_log import write_audit_log
from utils.validators import is_email_identifier
from utils.rate_limit import SlidingWindowRateLimiter

auth_bp = Blueprint("auth", __name__)

# Brute-force protection for the local login form. Failed attempts are counted
# per client IP and per username over a rolling window; a successful login clears
# the counters for that attempt.
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_IP_LIMIT = 10
_LOGIN_USER_LIMIT = 5
_login_limiter = SlidingWindowRateLimiter(_LOGIN_WINDOW_SECONDS)


def _login_rate_keys(username):
    ip = request.remote_addr or "unknown"
    ip_key = f"ip:{ip}"
    user_key = f"user:{username}" if username else None
    return ip, ip_key, user_key


def _clear_login_attempts(ip_key, user_key):
    _login_limiter.clear(ip_key)
    if user_key is not None:
        _login_limiter.clear(user_key)


def build_session_user(email, is_admin=False):
    email = email.lower()
    mapping = load_domain_mapping()
    delegated_domains = mapping.get(email, [])
    domain_grants = load_user_grants().get(email, {})
    resolved_admin = bool(
        is_admin
        or email in get_oidc_admin_users()
        or email == get_admin_user()
        or "*" in delegated_domains
    )
    return {
        "email": email,
        "is_admin": resolved_admin,
        "delegated_domains": delegated_domains,
        "domain_grants": domain_grants,
    }


def _start_user_session(user):
    """Establish an authenticated session, rotating session + CSRF state on login."""
    session.clear()
    session["user"] = user
    session["csrf_token"] = secrets.token_urlsafe(32)


@auth_bp.route("/login", methods=["GET", "POST"])
def login_page():
    if session.get("user"):
        return redirect(url_for("home"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        ip, ip_key, user_key = _login_rate_keys(username)
        blocked = _login_limiter.is_blocked(ip_key, _LOGIN_IP_LIMIT) or (
            user_key is not None
            and _login_limiter.is_blocked(user_key, _LOGIN_USER_LIMIT)
        )
        if blocked:
            write_audit_log(
                "auth.login_rate_limited",
                username or "unknown",
                username or "unknown",
                {"ip": ip},
            )
            error = "Too many login attempts. Please wait a few minutes and try again."
            return render_template("login.html", error=error), 429

        user_row = None
        try:
            with get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, email, password_hash, is_admin FROM users WHERE email = ?",
                    (username,),
                )
                user_row = cursor.fetchone()
        except Exception as e:
            current_app.logger.error(f"Error checking user in SQLite: {e}")

        if user_row and user_row[2]:  # password_hash exists
            if check_password_hash(user_row[2], password):
                _clear_login_attempts(ip_key, user_key)
                _start_user_session(build_session_user(user_row[1], bool(user_row[3])))
                write_audit_log("auth.login", user_row[1], user_row[1])
                return redirect(url_for("home"))

        # Fallback to local admin config check (hashed password only)
        if username == get_admin_user() and verify_admin_password(password):
            _clear_login_attempts(ip_key, user_key)
            _start_user_session(build_session_user(username, True))
            write_audit_log("auth.login", username, username)
            return redirect(url_for("home"))

        _login_limiter.register(ip_key)
        if user_key is not None:
            _login_limiter.register(user_key)
        write_audit_log(
            "auth.login_failed", username, username, {"reason": "invalid_credentials"}
        )
        error = "Invalid credentials. Please try again."

    return render_template("login.html", error=error)


@auth_bp.route("/login/redirect")
def login_redirect():
    if not is_oidc_enabled():
        return redirect(url_for("home"))
    try:
        config = get_oidc_config()
    except Exception as e:
        current_app.logger.error(f"OIDC provider configuration failed: {e}")
        return render_template(
            "login.html",
            error="Single sign-on is temporarily unavailable. Please try again later.",
        ), 500

    auth_endpoint = config.get("authorization_endpoint")
    if not auth_endpoint:
        return (
            "Error: OIDC provider configuration does not define authorization_endpoint",
            500,
        )

    # Prevent CSRF
    state = secrets.token_urlsafe(16)
    session["oidc_state"] = state

    params = {
        "client_id": get_oidc_client_id(),
        "response_type": "code",
        "scope": get_oidc_scopes(),
        "redirect_uri": get_oidc_redirect_uri(),
        "state": state,
    }

    auth_url = f"{auth_endpoint}?{urlencode(params)}"
    return redirect(auth_url)


def _oidc_csrf_error_response():
    state = request.args.get("state")
    expected_state = session.pop("oidc_state", None)
    if (
        not state
        or not expected_state
        or not secrets.compare_digest(state, expected_state)
    ):
        return "Authentication error: CSRF state verification failed", 400
    return None


def _oidc_fetch_userinfo(code):
    config = get_oidc_config()
    token_endpoint = config.get("token_endpoint")
    userinfo_endpoint = config.get("userinfo_endpoint")
    if not token_endpoint:
        return None, ("Error: OIDC token endpoint not configured", 500)

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": get_oidc_redirect_uri(),
        "client_id": get_oidc_client_id(),
        "client_secret": get_oidc_client_secret(),
    }
    token_res = requests.post(token_endpoint, data=payload, timeout=15)
    token_res.raise_for_status()
    token_data = token_res.json()

    access_token = token_data.get("access_token")
    if not access_token:
        return None, ("Error: OIDC token response did not contain access_token", 500)
    if not userinfo_endpoint:
        return None, ("Error: OIDC userinfo endpoint not configured", 500)

    userinfo_res = requests.get(
        userinfo_endpoint,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    userinfo_res.raise_for_status()
    return userinfo_res.json(), None


def _oidc_resolve_identity(userinfo_data):
    email = (
        userinfo_data.get("email")
        or userinfo_data.get("sub")
        or userinfo_data.get("preferred_username")
    )
    if not email:
        return None, ("Error: User identification claim not found in userinfo", 500)
    email = email.lower().strip()

    user_groups = userinfo_data.get("groups", [])
    if not isinstance(user_groups, list):
        user_groups = []
    is_admin = (email in get_oidc_admin_users()) or (
        get_oidc_admin_group() in user_groups
    )
    return (email, is_admin), None


def _oidc_sync_user_access(email, is_admin):
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, is_admin FROM users WHERE email = ?", (email,))
            user_row = cursor.fetchone()

            if is_admin:
                if not user_row:
                    cursor.execute(
                        "INSERT INTO users (email, is_admin) VALUES (?, 1)",
                        (email,),
                    )
                else:
                    cursor.execute(
                        "UPDATE users SET is_admin = 1 WHERE email = ?", (email,)
                    )
                conn.commit()
            elif not user_row:
                return None, render_template(
                    "login.html",
                    error="You do not have access to this tool. Please contact an administrator.",
                )
        return user_row, None
    except Exception as db_err:
        current_app.logger.error(
            f"Failed to query/insert OIDC user in database: {db_err}"
        )
        return None, (
            render_template(
                "login.html",
                error="Sign-in is temporarily unavailable. Please try again later.",
            ),
            503,
        )


@auth_bp.route("/oidc/callback")
def oidc_callback():
    if not is_oidc_enabled():
        return redirect(url_for("home"))

    csrf_error = _oidc_csrf_error_response()
    if csrf_error:
        return csrf_error

    code = request.args.get("code")
    if not code:
        return "Authentication error: Missing authorization code", 400

    try:
        userinfo, fetch_error = _oidc_fetch_userinfo(code)
        if fetch_error:
            return fetch_error[0], fetch_error[1]

        identity, identity_error = _oidc_resolve_identity(userinfo)
        if identity_error:
            return identity_error[0], identity_error[1]

        email, is_admin = identity
        user_row, access_error = _oidc_sync_user_access(email, is_admin)
        if access_error:
            return access_error

        _start_user_session(
            build_session_user(
                email,
                is_admin or bool(user_row and user_row[1]),
            )
        )

        write_audit_log("auth.login", email, email, {"method": "oidc"})
        return redirect(url_for("home"))
    except Exception as e:
        current_app.logger.error(f"OIDC flow callback failure: {e}")
        return render_template(
            "login.html",
            error="Authentication failed. Please try again or contact an administrator.",
        ), 500


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
