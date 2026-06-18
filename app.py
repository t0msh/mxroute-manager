import os
import secrets
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g, abort
from werkzeug.middleware.proxy_fix import ProxyFix

from dotenv import load_dotenv

from models.db import init_db, use_secure_cookies, get_or_create_secret_key, is_oidc_enabled, get_reset_portal_by_host
from app_meta import APP_VERSION, get_about_info, get_version_label
from utils.icons import icon
from routes import (
    auth_bp,
    domains_bp,
    emails_bp,
    spam_bp,
    cloudflare_bp,
    admin_bp,
    password_reset_bp,
    reset_portal_bp,
)
from services.mail import is_password_reset_available
from services.reset_portal import is_portal_allowed_path, get_portal_branding_context

load_dotenv()

app = Flask(__name__)


def _trusted_proxy_count():
    """Number of trusted reverse proxies in front of the app (0 disables ProxyFix)."""
    try:
        return max(0, int(os.getenv("TRUSTED_PROXY_COUNT", "1")))
    except (TypeError, ValueError):
        return 1


# Honor X-Forwarded-* from a known number of trusted proxies so request.remote_addr
# (and scheme/host) reflect the real client. Without this, X-Forwarded-For is
# attacker-controlled and would let clients spoof rate-limit keys.
_proxy_hops = _trusted_proxy_count()
if _proxy_hops > 0:
    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_for=_proxy_hops, x_proto=_proxy_hops, x_host=_proxy_hops
    )


# Baseline Content-Security-Policy. Inline scripts/styles and inline event handlers
# are still used in templates, so 'unsafe-inline' is required for now; the rest of
# the policy still blocks plugins, framing, and unexpected origins. Google Fonts is
# allowlisted because static/style.css imports it.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'self'",
    "img-src 'self' data:",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "script-src 'self' 'unsafe-inline'",
    "connect-src 'self'",
    "form-action 'self'",
])

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(domains_bp)
app.register_blueprint(emails_bp)
app.register_blueprint(spam_bp)
app.register_blueprint(cloudflare_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(password_reset_bp)
app.register_blueprint(reset_portal_bp)


PUBLIC_PATHS = frozenset({
    "/login",
    "/login/redirect",
    "/oidc/callback",
    "/logout",
    "/reset-password",
    "/api/public/password-reset/status",
    "/api/public/password-reset/request",
    "/api/public/password-reset/confirm",
    "/api/public/reset-portal/logo",
})

CSRF_EXEMPT_PATHS = frozenset({
    "/login",
    "/oidc/callback",
})


def _is_public_request():
    if request.path.startswith("/static/"):
        return True
    if request.path in PUBLIC_PATHS:
        return True
    if getattr(g, "reset_portal", None) and is_portal_allowed_path(request.path):
        return True
    return False


@app.before_request
def resolve_reset_portal():
    host = request.host.split(":", 1)[0].lower()
    portal = get_reset_portal_by_host(host)
    g.reset_portal = portal
    g.reset_portal_domain = portal["domain"] if portal else None
    if portal and not is_portal_allowed_path(request.path):
        abort(404)


@app.context_processor
def inject_app_meta():
    branding = get_portal_branding_context(getattr(g, "reset_portal", None))
    return {
        "app_version": APP_VERSION,
        "app_version_label": get_version_label(),
        "app_meta": get_about_info(),
        "icon": icon,
        **branding,
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
    if _is_public_request():
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


@app.after_request
def set_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # setdefault lets specific endpoints (e.g. the SVG logo) apply a stricter policy.
    response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    if use_secure_cookies():
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
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
    portal = getattr(g, "reset_portal", None)
    if portal:
        branding = get_portal_branding_context(portal)
        return render_template(
            "reset_portal.html",
            reset_available=is_password_reset_available(),
            **branding,
        )
    return render_template('index.html')


if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
