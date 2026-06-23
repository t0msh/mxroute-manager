from utils.apprise import compilers

NTFY_PRIORITIES = ("min", "low", "default", "high", "urgent", "max")

BUILDER_SERVICES = [
    {
        "id": "ntfy",
        "label": "ntfy",
        "description": "Self-hosted or ntfy.sh push notifications",
        "fields": [
            {"id": "host", "label": "Server", "type": "text", "placeholder": "ntfy.sh"},
            {"id": "topic", "label": "Topic", "type": "text", "required": True},
            {"id": "token", "label": "Auth token", "type": "secret"},
            {
                "id": "priority",
                "label": "Priority",
                "type": "select",
                "options": list(NTFY_PRIORITIES),
                "default": "default",
            },
            {
                "id": "tags",
                "label": "Tags",
                "type": "text",
                "placeholder": "mxroute,alert",
            },
            {"id": "secure", "label": "Use HTTPS", "type": "checkbox", "default": True},
        ],
        "compile": compilers.compile_ntfy,
    },
    {
        "id": "json",
        "label": "JSON Webhook",
        "description": "Generic HTTP JSON webhook (Apprise json://)",
        "fields": [
            {
                "id": "url",
                "label": "Webhook URL",
                "type": "text",
                "required": True,
                "placeholder": "https://hooks.example.com/mxroute",
            },
            {"id": "token", "label": "Bearer token", "type": "secret"},
            {
                "id": "auth_header",
                "label": "Auth header (optional)",
                "type": "secret",
                "placeholder": "Authorization: Bearer ...",
            },
            {"id": "secure", "label": "Use HTTPS", "type": "checkbox", "default": True},
        ],
        "compile": compilers.compile_json_webhook,
    },
    {
        "id": "discord",
        "label": "Discord",
        "description": "Discord webhook",
        "fields": [
            {
                "id": "webhook_id",
                "label": "Webhook ID",
                "type": "text",
                "required": True,
            },
            {
                "id": "webhook_token",
                "label": "Webhook token",
                "type": "secret",
                "required": True,
            },
        ],
        "compile": compilers.compile_discord,
    },
    {
        "id": "slack",
        "label": "Slack",
        "description": "Slack incoming webhook",
        "fields": [
            {
                "id": "webhook_url",
                "label": "Incoming webhook URL",
                "type": "text",
                "required": True,
            },
        ],
        "compile": compilers.compile_slack,
    },
    {
        "id": "gotify",
        "label": "Gotify",
        "description": "Gotify push notifications",
        "fields": [
            {"id": "host", "label": "Server", "type": "text", "required": True},
            {"id": "port", "label": "Port", "type": "text", "placeholder": "443"},
            {
                "id": "token",
                "label": "Application token",
                "type": "secret",
                "required": True,
            },
            {"id": "secure", "label": "Use HTTPS", "type": "checkbox", "default": True},
        ],
        "compile": compilers.compile_gotify,
    },
    {
        "id": "pushover",
        "label": "Pushover",
        "description": "Pushover notifications",
        "fields": [
            {"id": "user_key", "label": "User key", "type": "text", "required": True},
            {
                "id": "api_token",
                "label": "API token",
                "type": "secret",
                "required": True,
            },
        ],
        "compile": compilers.compile_pushover,
    },
    {
        "id": "telegram",
        "label": "Telegram",
        "description": "Telegram bot notifications",
        "fields": [
            {
                "id": "bot_token",
                "label": "Bot token",
                "type": "secret",
                "required": True,
            },
            {"id": "chat_id", "label": "Chat ID", "type": "text", "required": True},
        ],
        "compile": compilers.compile_telegram,
    },
    {
        "id": "mailto",
        "label": "Email (SMTP)",
        "description": "Email via SMTP",
        "fields": [
            {
                "id": "use_reset_smtp",
                "label": "Use Mailbox Password Reset SMTP settings",
                "type": "checkbox",
                "default": False,
            },
            {"id": "smtp_host", "label": "SMTP host", "type": "text"},
            {"id": "smtp_port", "label": "SMTP port", "type": "text", "default": "587"},
            {"id": "smtp_user", "label": "SMTP user", "type": "text"},
            {"id": "smtp_password", "label": "SMTP password", "type": "secret"},
            {"id": "from_email", "label": "From address", "type": "text"},
            {"id": "to_email", "label": "To address", "type": "text", "required": True},
        ],
        "compile": compilers.compile_mailto,
    },
    {
        "id": "custom",
        "label": "Custom Apprise URL",
        "description": "Paste any Apprise URL (see appriseit.com)",
        "fields": [
            {"id": "url", "label": "Apprise URL", "type": "text", "required": True},
        ],
        "compile": compilers.compile_custom,
    },
]

SERVICE_BY_ID = {service["id"]: service for service in BUILDER_SERVICES}


def builder_catalog_for_api():
    """Return service definitions without compile callables."""
    catalog = []
    for service in BUILDER_SERVICES:
        catalog.append(
            {
                "id": service["id"],
                "label": service["label"],
                "description": service.get("description", ""),
                "fields": service["fields"],
            }
        )
    return catalog
