"""Single source of truth for application metadata. Bump APP_VERSION here for releases."""

import os
from importlib.util import module_from_spec, spec_from_file_location

APP_VERSION = "0.16.0"
APP_NAME = "MXroute Manager"
APP_DESCRIPTION = (
    "Self-hosted control panel for MXroute email hosting, DNS management, "
    "delegated access, and branded password-reset portals."
)

GITHUB_URL = os.getenv("MXM_GITHUB_URL", "https://github.com/t0msh/mxroute-manager")
LICENSE_NAME = "MIT License"
LICENSE_URL = os.getenv("MXM_LICENSE_URL", "https://opensource.org/licenses/MIT")
COPYRIGHT = "Copyright (c) 2026 Tom Shute"

ATTRIBUTIONS = [
    {
        "name": "Bootstrap Icons",
        "description": "Open-source icon font used in the UI",
        "homepage": "https://icons.getbootstrap.com/",
    },
    {
        "name": "MXroute",
        "description": "Email hosting platform and domain/mailbox management API",
        "homepage": "https://mxroute.com/",
    },
    {
        "name": "Cloudflare",
        "description": "DNS zone management, proxied CNAME records, and optional Origin CA",
        "homepage": "https://www.cloudflare.com/",
    },
    {
        "name": "Nginx Proxy Manager",
        "description": "Reverse proxy hosts and TLS certificates for reset portals",
        "homepage": "https://nginxproxymanager.com/",
    },
    {
        "name": "Let's Encrypt",
        "description": "Free TLS certificates (DNS-01 challenge via NPM)",
        "homepage": "https://letsencrypt.org/",
    },
    {
        "name": "OpenID Connect",
        "description": "SSO authentication with your identity provider",
        "homepage": "https://openid.net/connect/",
    },
    {
        "name": "Flask",
        "description": "Web application framework",
        "homepage": "https://flask.palletsprojects.com/",
    },
    {
        "name": "Gunicorn",
        "description": "Production WSGI HTTP server",
        "homepage": "https://gunicorn.org/",
    },
    {
        "name": "dnspython",
        "description": "Public DNS lookups for health checks",
        "homepage": "https://www.dnspython.org/",
    },
    {
        "name": "Apprise",
        "description": "Multi-platform notification delivery for audit event alerts",
        "homepage": "https://github.com/caronc/apprise",
    },
]


def get_build_info():
    """Git stamp from build_info.py (empty when not populated)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build_info_path = os.path.join(root, "build_info.py")
    if not os.path.isfile(build_info_path):
        return {"sha": "", "branch": "", "describe": ""}
    spec = spec_from_file_location("build_info", build_info_path)
    if spec is None or spec.loader is None:
        return {"sha": "", "branch": "", "describe": ""}
    module = module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ImportError:
        return {"sha": "", "branch": "", "describe": ""}
    return {
        "sha": (getattr(module, "BUILD_SHA", "") or "").strip(),
        "branch": (getattr(module, "BUILD_BRANCH", "") or "").strip(),
        "describe": (getattr(module, "BUILD_DESCRIBE", "") or "").strip(),
    }


def get_commit_url(sha: str = "") -> str:
    sha = (sha or get_build_info()["sha"]).strip()
    if not sha or "github.com" not in GITHUB_URL:
        return ""
    return f"{GITHUB_URL.rstrip('/')}/commit/{sha}"


def get_version_label() -> str:
    """Short UI label: v0.9.2 or v0.9.2 · dev@47d575a when build_info is populated."""
    label = f"v{APP_VERSION}"
    build = get_build_info()
    sha, branch = build["sha"], build["branch"]
    if sha and branch and branch != "main":
        return f"{label} · {branch}@{sha}"
    if sha:
        return f"{label} · {sha}"
    return label


def get_about_info():
    build = get_build_info()
    commit_url = get_commit_url(build["sha"])
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "version_label": get_version_label(),
        "build": build,
        "commit_url": commit_url,
        "description": APP_DESCRIPTION,
        "github_url": GITHUB_URL,
        "license_name": LICENSE_NAME,
        "license_url": LICENSE_URL,
        "copyright": COPYRIGHT,
        "attributions": ATTRIBUTIONS,
    }
