# App tour

A visual overview of MXroute Manager after login. Screenshots use the **Emerald Glass** workspace theme unless noted. For all login and theme variants, see [Themes](themes.md).

The **global domain selector** at the top of most tabs sets which domain you are managing. Dashboard, Email Accounts, Forwarders, and Spam Controls all respect that selection.

## Dashboard

Overview of the active domain: mail hosting toggle, mailbox count, DNS health, and account quota usage. With two or more domains, a **Fleet overview** table shows mail routing, DNS status, and mailbox counts across the account (click a row to switch domains). Details: [Fleet overview](fleet-overview.md).

![Dashboard](images/app-tour/dashboard.png)

## Domains

Domain and DNS setup wizard, **Active Domains** list (search + pagination), bulk DNS fix, and password reset portal configuration. See [Adding a domain](adding-a-domain.md) for the full onboarding walkthrough.

![Domains tab](images/app-tour/tab-domains.png)

### Password reset portal (admin)

Configure a branded reset page on a subdomain. Example from `actualrealwebsite.com`:

![Reset portal configuration](images/app-tour/domains-reset-portal-actualrealwebsite.png)

### Password reset portal (public)

Live portal served at the subdomain after deploy:

![Live reset portal](images/app-tour/reset-portal-actualrealwebsite.png)

## Email Accounts

Provision mailboxes, view usage and limits, search and paginate the **Active Mailboxes** list, **import or export CSV**, and open per-mailbox actions (including **Client setup** for IMAP/SMTP settings).

![Email Accounts tab](images/app-tour/tab-emails.png)

### Mailbox actions menu

Client setup, recovery email, password, limits, and delete:

![Mailbox actions menu](images/app-tour/mailbox-actions-menu.png)

## Forwarders

Catch-all routing, alias forwarders, and domain pointers.

![Forwarders tab](images/app-tour/tab-forwarders.png)

### Add domain pointer

![Add domain pointer modal](images/app-tour/modal-add-pointer.png)

## Spam Controls

SpamAssassin threshold, whitelist, and blacklist for the active domain.

![Spam Controls tab](images/app-tour/tab-spam.png)

## Access Control

Create delegated users, assign per-domain permissions, and manage **API tokens** for automation.

![Access Control tab](images/app-tour/tab-delegations.png)

See [Access control](access-control.md) for permission details and [HTTP API](api.md) for scripting.

## Notifications

Configure Apprise delivery targets, audit event subscriptions, and optional **DNS health monitoring** (scheduled checks with alert/recovery notifications). See [Notifications](notifications.md).

![Notifications tab](images/app-tour/tab-notifications.png)

## Logs

Audit log of sign-ins, config changes, and admin actions. Filterable, optionally auto-refreshed, and downloadable as CSV or JSONL for the full day. See [Audit logs](audit-logs.md).

![Logs tab](images/app-tour/tab-logs.png)

## Settings

MXroute and Cloudflare API settings, OIDC, SMTP for mailbox reset, local admin password, **API reference** link, and **theme selection**. Field-by-field guide: [Settings walkthrough](settings-walkthrough.md).

![Settings tab](images/app-tour/tab-settings.png)

![Theme picker](images/app-tour/settings-themes.png)

## Common modals

These dialogs appear from Email Accounts and other tabs.

### Update password

![Update password modal](images/app-tour/modal-update-password.png)

### Recovery email

![Recovery email modal](images/app-tour/modal-update-recovery.png)

### Adjust quota and send limit

![Quota modal](images/app-tour/modal-update-quota.png)

### Confirm deletion (typed)

Destructive actions require typing the mailbox address to confirm:

![Typed confirm delete](images/app-tour/modal-typed-confirm-delete.png)

## Related guides

| Guide | Topic |
| --- | --- |
| [HTTP API](api.md) | Bearer tokens and curl examples |
| [Themes](themes.md) | All 12 login screen themes |
| [Adding a domain](adding-a-domain.md) | Domain wizard step by step |
| [Access control](access-control.md) | Delegated users |
| [Password reset](password-reset.md) | Self-service and branded portals |
| [Getting started](getting-started.md) | Install and first login |
