"""Single source of truth for application metadata. Bump APP_VERSION here for releases."""

APP_VERSION = "0.1.0"
APP_NAME = "MXroute Manager"
APP_DESCRIPTION = "Self-hosted control panel for MXroute email hosting and DNS management."

GITHUB_URL = "https://github.com/t0msh/mxroute-manager"
LICENSE_NAME = "MIT License"
LICENSE_URL = "https://opensource.org/licenses/MIT"
COPYRIGHT = "Copyright (c) 2026 Tom Shute"

ATTRIBUTIONS = [
    {
        "name": "MXroute",
        "description": "Email hosting platform and management API",
        "url": "https://mxroute.com/",
    },
    {
        "name": "Cloudflare",
        "description": "DNS zone and record management API",
        "url": "https://www.cloudflare.com/",
    },
    {
        "name": "Flask",
        "description": "Web application framework",
        "url": "https://flask.palletsprojects.com/",
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
