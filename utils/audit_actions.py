"""Catalog of audit log action types for notifications UI and subscriptions."""

AUDIT_ACTIONS = [
    # Authentication
    {
        "id": "auth.login",
        "label": "User login",
        "group": "Authentication",
        "description": "Successful local or OIDC login",
    },
    {
        "id": "auth.login_failed",
        "label": "Login failed",
        "group": "Authentication",
        "description": "Invalid credentials",
    },
    {
        "id": "auth.login_rate_limited",
        "label": "Login rate limited",
        "group": "Authentication",
        "description": "Too many failed attempts from an IP",
    },
    {"id": "auth.logout", "label": "User logout", "group": "Authentication"},
    # Profile
    {
        "id": "profile.update",
        "label": "Profile updated",
        "group": "Profile",
        "description": "Contact email changed",
    },
    # Access control / settings
    {
        "id": "delegation.update",
        "label": "Delegation updated",
        "group": "Access control",
        "description": "User grants or admin flag changed",
    },
    {
        "id": "delegation.revoke",
        "label": "Delegation revoked",
        "group": "Access control",
        "description": "User access removed",
    },
    {
        "id": "settings.update",
        "label": "System settings updated",
        "group": "Settings",
        "description": "Includes admin password when changed",
    },
    {
        "id": "settings.admin_password_update",
        "label": "Admin password updated",
        "group": "Settings",
    },
    {"id": "settings.smtp_test", "label": "SMTP test sent", "group": "Settings"},
    # Domains
    {"id": "domain.create", "label": "Domain added", "group": "Domains"},
    {"id": "domain.delete", "label": "Domain deleted", "group": "Domains"},
    {
        "id": "domain.mail_status",
        "label": "Domain mail status changed",
        "group": "Domains",
    },
    {"id": "pointer.create", "label": "Domain pointer created", "group": "Domains"},
    {"id": "pointer.delete", "label": "Domain pointer deleted", "group": "Domains"},
    # Mailboxes
    {"id": "mailbox.create", "label": "Mailbox created", "group": "Mailboxes"},
    {"id": "mailbox.update", "label": "Mailbox updated", "group": "Mailboxes"},
    {
        "id": "mailbox.password_update",
        "label": "Mailbox password updated",
        "group": "Mailboxes",
    },
    {
        "id": "mailbox.quota_update",
        "label": "Mailbox quota updated",
        "group": "Mailboxes",
    },
    {"id": "mailbox.delete", "label": "Mailbox deleted", "group": "Mailboxes"},
    {
        "id": "mailbox.recovery_update",
        "label": "Mailbox recovery email updated",
        "group": "Mailboxes",
    },
    {
        "id": "mailbox.reset_requested",
        "label": "Password reset requested",
        "group": "Mailboxes",
        "description": "Public reset flow",
    },
    {
        "id": "mailbox.reset_completed",
        "label": "Password reset completed",
        "group": "Mailboxes",
        "description": "Public reset flow",
    },
    # Forwarders
    {"id": "forwarder.create", "label": "Forwarder created", "group": "Forwarders"},
    {"id": "forwarder.delete", "label": "Forwarder deleted", "group": "Forwarders"},
    {"id": "catchall.update", "label": "Catch-all updated", "group": "Forwarders"},
    # Spam
    {"id": "spam.settings_update", "label": "Spam settings updated", "group": "Spam"},
    {
        "id": "spam.whitelist_add",
        "label": "Spam whitelist entry added",
        "group": "Spam",
    },
    {
        "id": "spam.whitelist_remove",
        "label": "Spam whitelist entry removed",
        "group": "Spam",
    },
    {
        "id": "spam.blacklist_add",
        "label": "Spam blacklist entry added",
        "group": "Spam",
    },
    {
        "id": "spam.blacklist_remove",
        "label": "Spam blacklist entry removed",
        "group": "Spam",
    },
    # DNS / Cloudflare
    {"id": "cloudflare.setup", "label": "Cloudflare DNS setup", "group": "DNS"},
    {"id": "dns.fix", "label": "DNS records fixed", "group": "DNS"},
    {
        "id": "reset_portal.dns_deploy",
        "label": "Reset portal DNS deployed",
        "group": "DNS",
    },
    {
        "id": "reset_portal.dns_remove",
        "label": "Reset portal DNS removed",
        "group": "DNS",
    },
    # Reset portal
    {
        "id": "reset_portal.deploy",
        "label": "Reset portal deployed",
        "group": "Reset portal",
    },
    {
        "id": "reset_portal.teardown",
        "label": "Reset portal torn down",
        "group": "Reset portal",
    },
    # System
    {"id": "smtp.send_failed", "label": "SMTP send failed", "group": "System"},
    {"id": "notification.test", "label": "Notification test", "group": "System"},
    {
        "id": "notification.send_failed",
        "label": "Notification send failed",
        "group": "System",
    },
]

DESTRUCTIVE_ACTION_IDS = frozenset(
    {
        "domain.delete",
        "mailbox.delete",
        "forwarder.delete",
        "pointer.delete",
        "delegation.revoke",
        "reset_portal.teardown",
        "reset_portal.dns_remove",
        "spam.whitelist_remove",
        "spam.blacklist_remove",
    }
)


def grouped_audit_actions():
    """Return actions grouped by ``group`` for the settings UI."""
    groups = {}
    for action in AUDIT_ACTIONS:
        group = action["group"]
        groups.setdefault(group, []).append(action)
    return [{"group": name, "actions": items} for name, items in groups.items()]


def audit_action_ids():
    return {action["id"] for action in AUDIT_ACTIONS}
