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


def get_about_info():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "description": APP_DESCRIPTION,
        "github_url": GITHUB_URL,
        "license_name": LICENSE_NAME,
        "license_url": LICENSE_URL,
        "copyright": COPYRIGHT,
        "attributions": ATTRIBUTIONS,
    }
