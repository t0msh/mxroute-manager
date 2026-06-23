import os

from flask import Blueprint, request, jsonify, g, send_file, abort

from models.db import (
    get_reset_portal,
    upsert_reset_portal,
    set_reset_portal_logo,
    clear_reset_portal_logo,
)
from services.cloudflare import cf_is_configured, check_reset_portal_dns
from services.reset_portal_deploy import (
    deploy_reset_portal,
    teardown_reset_portal,
    missing_deploy_config,
    reset_portal_deploy_is_configured,
    check_reset_portal_https_quick,
)
from services.cf_origin_ca import cf_origin_ca_is_configured
from services.reverse_proxy import (
    get_backend,
    get_backend_id,
    portal_cname_target,
    proxy_is_configured,
)
from services.reverse_proxy.manual import manual_snippets
from services.reset_portal import (
    ALLOWED_LOGO_EXTENSIONS,
    MAX_LOGO_BYTES,
    branding_path_for_domain,
    logo_path_for_portal,
)
from utils.validators import (
    public_https_origin,
    validate_domain,
    validate_subdomain_prefix,
)
from models.db import get_user_contact_email, resolve_notification_email
from utils.auth_helpers import require_permission, get_current_user
from utils.themes import normalize_theme, DEFAULT_THEME

reset_portal_bp = Blueprint("reset_portal", __name__)

# Logos may be SVG, which can embed scripts. Serving them under a sandbox CSP
# neutralizes any embedded script even if the file is opened directly, while still
# rendering fine inside an <img> tag.
_LOGO_SANDBOX_CSP = "default-src 'none'; style-src 'unsafe-inline'; sandbox"


def _serve_logo(logo_path, mimetype, max_age):
    response = send_file(logo_path, mimetype=mimetype, max_age=max_age)
    response.headers["Content-Security-Policy"] = _LOGO_SANDBOX_CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _safe_status(check_fn, *args, **kwargs):
    try:
        return check_fn(*args, **kwargs)
    except Exception:
        return {"status": "unknown", "message": "Status check failed."}


def _ensure_reset_portal_draft(domain):
    """Create a disabled portal row so branding (e.g. logo) can be saved before deploy."""
    portal = get_reset_portal(domain)
    if portal:
        return portal
    upsert_reset_portal(domain, False, "", "", DEFAULT_THEME)
    return get_reset_portal(domain)


def _portal_proxy_fields():
    backend = get_backend()
    return {
        "proxy_backend": get_backend_id(),
        "proxy_display_name": backend.display_name,
        "proxy_configured": proxy_is_configured(),
        "origin_ca_configured": cf_origin_ca_is_configured()
        and backend.supports_origin_ca(),
    }


def _portal_response(portal, include_live_checks=True):
    proxy_fields = _portal_proxy_fields()
    base = {
        "cname_target": portal_cname_target(),
        "cf_configured": cf_is_configured(),
        "deploy_configured": reset_portal_deploy_is_configured(),
        "deploy_missing": missing_deploy_config(),
        **proxy_fields,
        # Backward compatibility for older UI/scripts
        "npm_configured": proxy_fields["proxy_configured"]
        and proxy_fields["proxy_backend"] == "npm",
    }
    if not portal:
        return {
            "domain": "",
            "enabled": False,
            "subdomain_prefix": "",
            "portal_host": "",
            "portal_title": "",
            "portal_theme": DEFAULT_THEME,
            "has_logo": False,
            "portal_url": "",
            "dns": None,
            "https": None,
            "manual_snippets": None,
            **base,
        }
    host = portal.get("portal_host") or ""
    live = include_live_checks and portal.get("enabled") and host
    dns = _safe_status(check_reset_portal_dns, portal) if live else None
    https = None
    if live:
        if dns and dns.get("status") in ("pass", "warn"):
            https = _safe_status(check_reset_portal_https_quick, host)
        else:
            https = {
                "status": "pending",
                "message": (
                    "Deploy DNS and reverse proxy first; HTTPS is checked after the CNAME is live."
                ),
            }
    manual = None
    if proxy_fields["proxy_backend"] == "manual" and host:
        manual = manual_snippets(host)
    return {
        "domain": portal["domain"],
        "enabled": portal["enabled"],
        "subdomain_prefix": portal.get("subdomain_prefix") or "",
        "portal_host": host,
        "portal_title": portal.get("portal_title") or "",
        "portal_theme": normalize_theme(portal.get("portal_theme")),
        "has_logo": bool(portal.get("logo_filename")),
        "portal_url": public_https_origin(host),
        "dns": dns,
        "https": https,
        "manual_snippets": manual,
        **base,
    }


@reset_portal_bp.route("/api/domains/<domain>/reset-portal", methods=["GET"])
@require_permission("dns")
def get_domain_reset_portal(domain):
    if not validate_domain(domain):
        return jsonify(
            {"success": False, "error": {"message": "Invalid domain name format"}}
        ), 400
    portal = get_reset_portal(domain)
    return jsonify({"success": True, "data": _portal_response(portal)})


@reset_portal_bp.route("/api/domains/<domain>/reset-portal", methods=["PATCH"])
@require_permission("dns")
def update_domain_reset_portal(domain):
    if not validate_domain(domain):
        return jsonify(
            {"success": False, "error": {"message": "Invalid domain name format"}}
        ), 400

    data = request.json or {}
    enabled = bool(data.get("enabled"))
    subdomain_prefix = (data.get("subdomain_prefix") or "").strip().lower()
    portal_title = (data.get("portal_title") or "").strip()
    portal_theme = normalize_theme(data.get("portal_theme"))

    if enabled and not subdomain_prefix:
        return jsonify(
            {
                "success": False,
                "error": {
                    "message": "Subdomain prefix is required when the portal is enabled."
                },
            }
        ), 400
    if subdomain_prefix:
        ok, message = validate_subdomain_prefix(subdomain_prefix)
        if not ok:
            return jsonify({"success": False, "error": {"message": message}}), 400

    portal_before = get_reset_portal(domain)
    was_enabled = bool(portal_before and portal_before.get("enabled"))

    ok, message = upsert_reset_portal(
        domain, enabled, subdomain_prefix, portal_title, portal_theme
    )
    if not ok:
        return jsonify({"success": False, "error": {"message": message}}), 400

    teardown_steps = []
    if was_enabled and not enabled and portal_before.get("portal_host"):
        teardown_result = teardown_reset_portal(domain, portal_before)
        teardown_steps = teardown_result.get("steps") or []

    portal = get_reset_portal(domain)
    data = _portal_response(portal)
    if teardown_steps:
        data["teardown_steps"] = teardown_steps
    return jsonify({"success": True, "data": data})


@reset_portal_bp.route("/api/domains/<domain>/reset-portal/logo", methods=["POST"])
@require_permission("dns")
def upload_reset_portal_logo(domain):
    if not validate_domain(domain):
        return jsonify(
            {"success": False, "error": {"message": "Invalid domain name format"}}
        ), 400

    portal = _ensure_reset_portal_draft(domain)
    if not portal:
        return jsonify(
            {
                "success": False,
                "error": {"message": "Failed to initialize portal settings."},
            }
        ), 500

    upload = request.files.get("logo")
    if not upload or not upload.filename:
        return jsonify(
            {"success": False, "error": {"message": "Logo file is required."}}
        ), 400

    ext = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        return jsonify(
            {
                "success": False,
                "error": {"message": "Logo must be PNG, JPEG, WebP, or SVG."},
            }
        ), 400

    data = upload.read(MAX_LOGO_BYTES + 1)
    if len(data) > MAX_LOGO_BYTES:
        return jsonify(
            {"success": False, "error": {"message": "Logo must be 512 KB or smaller."}}
        ), 400

    branding_dir = branding_path_for_domain(domain)
    os.makedirs(branding_dir, exist_ok=True)

    if portal.get("logo_filename"):
        old_path = os.path.join(branding_dir, portal["logo_filename"])
        if os.path.isfile(old_path):
            os.remove(old_path)

    filename = f"logo.{ext}"
    logo_path = os.path.join(branding_dir, filename)
    with open(logo_path, "wb") as handle:
        handle.write(data)

    set_reset_portal_logo(domain, filename)
    portal = get_reset_portal(domain)
    return jsonify({"success": True, "data": _portal_response(portal)})


@reset_portal_bp.route("/api/domains/<domain>/reset-portal/logo", methods=["DELETE"])
@require_permission("dns")
def delete_reset_portal_logo(domain):
    if not validate_domain(domain):
        return jsonify(
            {"success": False, "error": {"message": "Invalid domain name format"}}
        ), 400
    clear_reset_portal_logo(domain)
    portal = get_reset_portal(domain)
    return jsonify({"success": True, "data": _portal_response(portal)})


@reset_portal_bp.route(
    "/api/domains/<domain>/reset-portal/deploy-dns", methods=["POST"]
)
@require_permission("dns")
def deploy_reset_portal_dns(domain):
    if not validate_domain(domain):
        return jsonify(
            {"success": False, "error": {"message": "Invalid domain name format"}}
        ), 400

    portal = get_reset_portal(domain)
    if not portal or not portal.get("enabled"):
        return jsonify(
            {
                "success": False,
                "error": {"message": "Enable the reset portal before deploying."},
            }
        ), 400
    if not portal.get("subdomain_prefix"):
        return jsonify(
            {"success": False, "error": {"message": "Subdomain prefix is required."}}
        ), 400

    missing = missing_deploy_config()
    if missing:
        return jsonify(
            {
                "success": False,
                "error": {
                    "message": "Reset portal deploy is not fully configured: "
                    + ", ".join(missing),
                },
            }
        ), 400

    current_user = get_current_user()
    login_identifier = (current_user or {}).get("email", "").strip().lower()
    admin_email = resolve_notification_email(
        login_identifier,
        get_user_contact_email(login_identifier),
    )
    if not admin_email:
        return jsonify(
            {
                "success": False,
                "error": {
                    "message": (
                        "No deliverable contact email for your account. "
                        "Add a contact email in Settings or Access Control, "
                        "or sign in with an email-based login."
                    ),
                },
            }
        ), 400

    try:
        result = deploy_reset_portal(
            domain, portal["subdomain_prefix"], admin_email=admin_email
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return jsonify({"success": False, "error": {"message": str(exc)}}), 400


@reset_portal_bp.route(
    "/api/domains/<domain>/reset-portal/logo-preview", methods=["GET"]
)
@require_permission("dns")
def preview_reset_portal_logo(domain):
    if not validate_domain(domain):
        return jsonify(
            {"success": False, "error": {"message": "Invalid domain name format"}}
        ), 400
    portal = get_reset_portal(domain)
    logo_path = logo_path_for_portal(portal)
    if not logo_path or not os.path.isfile(logo_path):
        abort(404)
    ext = portal["logo_filename"].rsplit(".", 1)[-1].lower()
    mimetype = ALLOWED_LOGO_EXTENSIONS.get(ext, "application/octet-stream")
    return _serve_logo(logo_path, mimetype, max_age=60)


@reset_portal_bp.route("/api/public/reset-portal/logo", methods=["GET"])
def public_reset_portal_logo():
    portal = getattr(g, "reset_portal", None)
    if not portal:
        abort(404)
    logo_path = logo_path_for_portal(portal)
    if not logo_path or not os.path.isfile(logo_path):
        abort(404)
    ext = portal["logo_filename"].rsplit(".", 1)[-1].lower()
    mimetype = ALLOWED_LOGO_EXTENSIONS.get(ext, "application/octet-stream")
    return _serve_logo(logo_path, mimetype, max_age=3600)
