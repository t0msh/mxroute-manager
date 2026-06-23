import os

DATABASE_FILE = os.getenv(
    "DATABASE_FILE",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "mxroute-manager.db",
    ),
)
MAPPING_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "domain_mapping.json"
)

ALL_PERMISSIONS = ("dashboard", "emails", "forwarders", "spam", "dns")
DEFAULT_PERMISSIONS = list(ALL_PERMISSIONS)

ENV_ONLY_SECRET_KEYS = frozenset(
    {
        "MX_API_KEY",
        "CF_API_TOKEN",
        "CF_ORIGIN_CA_KEY",
        "OIDC_CLIENT_SECRET",
        "NPM_SECRET",
        "RESET_SMTP_PASSWORD",
    }
)
MASKED_SECRET_KEYS = ENV_ONLY_SECRET_KEYS | frozenset(
    {
        "ADMIN_PASSWORD",
        "SECRET_KEY",
    }
)
ADMIN_PASSWORD_HASH_KEY = "ADMIN_PASSWORD_HASH"
RESET_TOKEN_TTL_HOURS = 1
SETTINGS_UI_KEYS = [
    "OIDC_ENABLED",
    "OIDC_CLIENT_ID",
    "OIDC_DISCOVERY_URL",
    "OIDC_REDIRECT_URI",
    "OIDC_SCOPES",
    "OIDC_ADMIN_USERS",
    "OIDC_ADMIN_GROUP",
    "MX_SERVER",
    "MX_USER",
    "CF_ACCOUNT_ID",
    "ADMIN_USER",
    "MAILBOX_RESET_ENABLED",
    "RESET_SMTP_HOST",
    "RESET_SMTP_PORT",
    "RESET_SMTP_USER",
    "RESET_SMTP_FROM",
    "RESET_SMTP_USE_TLS",
]
SETTINGS_RESPONSE_KEYS = SETTINGS_UI_KEYS + sorted(MASKED_SECRET_KEYS)
NOTIFICATION_SETTINGS_KEY = "NOTIFICATION_SETTINGS"
