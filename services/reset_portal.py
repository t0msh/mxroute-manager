import os

from flask import g

from models.db import get_branding_dir
from utils.themes import normalize_theme, DEFAULT_THEME

RESET_PORTAL_ALLOWED_PATHS = frozenset({
    "/",
    "/reset-password",
    "/api/public/password-reset/status",
    "/api/public/password-reset/request",
    "/api/public/password-reset/confirm",
    "/api/public/reset-portal/logo",
})

ALLOWED_LOGO_EXTENSIONS = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "svg": "image/svg+xml",
}
MAX_LOGO_BYTES = 512 * 1024


def is_reset_portal_request():
    return bool(getattr(g, "reset_portal", None))


def is_portal_allowed_path(path):
    if path.startswith("/static/"):
        return True
    return path in RESET_PORTAL_ALLOWED_PATHS


def get_portal_branding_context(portal):
    if not portal:
        return {
            "portal_title": "",
            "portal_logo_url": None,
            "portal_domain": "",
            "portal_theme": DEFAULT_THEME,
            "is_reset_portal": False,
        }
    title = (portal.get("portal_title") or "").strip() or portal["domain"]
    logo_url = None
    if portal.get("logo_filename"):
        logo_url = "/api/public/reset-portal/logo"
    return {
        "portal_title": title,
        "portal_logo_url": logo_url,
        "portal_domain": portal["domain"],
        "portal_theme": normalize_theme(portal.get("portal_theme")),
        "is_reset_portal": True,
    }


def branding_path_for_domain(domain):
    return os.path.join(get_branding_dir(), domain.lower().strip())


def logo_path_for_portal(portal):
    if not portal or not portal.get("logo_filename"):
        return None
    return os.path.join(branding_path_for_domain(portal["domain"]), portal["logo_filename"])
