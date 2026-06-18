import os
import secrets
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv

from models.db import init_db, use_secure_cookies, get_or_create_secret_key, is_oidc_enabled
from app_meta import APP_VERSION, get_about_info
from routes import auth_bp, domains_bp, emails_bp, spam_bp, cloudflare_bp, admin_bp, password_reset_bp

load_dotenv()

app = Flask(__name__)

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(domains_bp)
app.register_blueprint(emails_bp)
app.register_blueprint(spam_bp)
app.register_blueprint(cloudflare_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(password_reset_bp)


PUBLIC_PATHS = frozenset({
    "/login",
    "/login/redirect",
    "/oidc/callback",
    "/logout",
    "/reset-password",
    "/api/public/password-reset/status",
    "/api/public/password-reset/request",
    "/api/public/password-reset/confirm",
})

CSRF_EXEMPT_PATHS = frozenset({
    "/login",
    "/oidc/callback",
})


@app.context_processor
def inject_app_meta():
    return {
        "app_version": APP_VERSION,
        "app_meta": get_about_info(),
    }


# Flask Session security key and session cookies hardening
app.secret_key = get_or_create_secret_key()

app.config.update(
    SESSION_COOKIE_SECURE=use_secure_cookies(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

# Run database initialization
init_db(app.logger)


# Route interceptor to enforce login globally
@app.before_request
def check_authentication():
    # Exclude asset paths, authentication logic endpoints (including blueprints paths)
    if request.path.startswith('/static/') or request.path in PUBLIC_PATHS:
        return

    user = session.get('user')
    if not user:
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "error": {"message": "Unauthorized"}}), 401
        return redirect(url_for('auth.login_page'))


# CSRF protection implementation
@app.before_request
def generate_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)


@app.context_processor
def inject_global_vars():
    return dict(csrf_token=session.get("csrf_token"), oidc_enabled=is_oidc_enabled())


@app.after_request
def set_csrf_cookie(response):
    if "csrf_token" in session:
        response.set_cookie("csrf_token", session["csrf_token"], samesite="Lax", secure=use_secure_cookies())
    return response


@app.before_request
def csrf_protect():
    # Only protect state-changing methods
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        # Exclude specific paths like login endpoints
        if request.path in CSRF_EXEMPT_PATHS:
            return

        token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        expected_token = session.get("csrf_token")

        if not expected_token or not token or not secrets.compare_digest(expected_token, token):
            return jsonify({"success": False, "error": {"message": "Bad Request: CSRF token missing or invalid"}}), 400


@app.route('/')
def home():
    return render_template('index.html')


if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
