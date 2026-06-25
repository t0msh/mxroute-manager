from werkzeug.security import check_password_hash
from flask import request, session, redirect, url_for, render_template, current_app

from models.db import get_admin_user, get_conn, verify_admin_password
from routes.auth_blueprint import auth_bp
from routes.auth_session import build_session_user, start_user_session
from utils.audit_log import write_audit_log
from utils.rate_limit import SlidingWindowRateLimiter

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

        if user_row and user_row[2]:
            if check_password_hash(user_row[2], password):
                _clear_login_attempts(ip_key, user_key)
                start_user_session(build_session_user(user_row[1], bool(user_row[3])))
                write_audit_log("auth.login", user_row[1], user_row[1])
                return redirect(url_for("home"))

        if username == get_admin_user() and verify_admin_password(password):
            _clear_login_attempts(ip_key, user_key)
            start_user_session(build_session_user(username, True))
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
