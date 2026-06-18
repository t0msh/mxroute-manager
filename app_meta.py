"""Single source of truth for application metadata. Bump APP_VERSION here for releases."""

APP_VERSION = "0.9.2"
APP_NAME = "MXroute Manager"
APP_DESCRIPTION = (
    "Self-hosted control panel for MXroute email hosting, DNS management, "
    "delegated access, and branded password-reset portals."
)

GITHUB_URL = "https://github.com/t0msh/mxroute-manager"
LICENSE_NAME = "MIT License"
LICENSE_URL = "https://opensource.org/licenses/MIT"
COPYRIGHT = "Copyright (c) 2026 Tom Shute"

ATTRIBUTIONS = [
    {
        "name": "Bootstrap Icons",
        "description": "Open-source icon font used in the UI",
        "url": "https://icons.getbootstrap.com/",
    },
    {
        "name": "MXroute",
        "description": "Email hosting platform and domain/mailbox management API",
        "url": "https://mxroute.com/",
    },
    {
        "name": "Cloudflare",
        "description": "DNS zone management, proxied CNAME records, and optional Origin CA",
        "url": "https://www.cloudflare.com/",
    },
    {
        "name": "Nginx Proxy Manager",
        "description": "Reverse proxy hosts and TLS certificates for reset portals",
        "url": "https://nginxproxymanager.com/",
    },
    {
        "name": "Let's Encrypt",
        "description": "Free TLS certificates (DNS-01 challenge via NPM)",
        "url": "https://letsencrypt.org/",
    },
    {
        "name": "OpenID Connect",
        "description": "SSO authentication with your identity provider",
        "url": "https://openid.net/connect/",
    },
    {
        "name": "Flask",
        "description": "Web application framework",
        "url": "https://flask.palletsprojects.com/",
    },
    {
        "name": "Gunicorn",
        "description": "Production WSGI HTTP server",
        "url": "https://gunicorn.org/",
    },
    {
        "name": "dnspython",
        "description": "Public DNS lookups for health checks",
        "url": "https://www.dnspython.org/",
    },
]


def get_build_info():
    """Git stamp from build_info.py (empty when not populated)."""
    try:
        from build_info import BUILD_BRANCH, BUILD_DESCRIBE, BUILD_SHA
    except ImportError:
        return {"sha": "", "branch": "", "describe": ""}
    return {
        "sha": (BUILD_SHA or "").strip(),
        "branch": (BUILD_BRANCH or "").strip(),
        "describe": (BUILD_DESCRIBE or "").strip(),
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
