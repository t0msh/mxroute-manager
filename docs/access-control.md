# Access control

MXroute Manager separates **administrators** (full account access) from **delegated users** (scoped to specific domains and permissions). Permissions are enforced on every API route and reflected in the UI - delegated users only see tabs and actions they are allowed to use.

## Roles at a glance

| Role | How it is granted | Scope |
| --- | --- | --- |
| **Administrator** | `ADMIN_USER` / OIDC admin list / OIDC admin group / **Admin access** checkbox in Access Control | All domains and all features |
| **Delegated user** | Created in **Access Control** with per-domain permissions | Only assigned domains; only assigned permissions per domain |

Administrators always bypass permission checks. Delegated users never see **Access Control**, **Audit Logs**, or account-wide quota controls.

## Who counts as an admin

A signed-in user is treated as an administrator when any of the following is true:

- Their login identifier matches `ADMIN_USER` (default `admin`), including the break-glass local admin password path.
- Their email is listed in `OIDC_ADMIN_USERS`.
- Their OIDC `groups` claim includes `OIDC_ADMIN_GROUP` (default `administrators`).
- They have **Admin access** enabled in **Access Control** (stored as `is_admin` with a `*` domain grant).

OIDC users who are not in one of the admin paths must already exist in the database (created via Access Control) or login is rejected.

## Authentication methods

Delegated users can sign in in two ways, depending on how you configure the app:

### Local credentials

Use a **username** (`billy`), **pseudo-email** (`billy@local`), or a real email address as the login identifier. Local users need a password set when they are created (or when editing a user who has no password yet).

When `OIDC_ENABLED=true`, identifiers that look like real email addresses (`user@example.com`) are expected to use OIDC instead - local passwords are not required for those accounts unless you explicitly set one.

### OIDC / SSO

When OIDC is enabled, users with email-style identifiers sign in through your identity provider. They must be pre-provisioned under **Access Control** unless they qualify as an admin via `OIDC_ADMIN_USERS` or `OIDC_ADMIN_GROUP`.

## Configuring delegated access

Only administrators can open the **Access Control** tab.

### Add or edit a user

1. Open **Access Control**.
2. Enter a **username or email** (see [Authentication methods](#authentication-methods)).
3. Optionally set a **contact email** for notifications (falls back to the login identifier when it is already an email).
4. Set a **local password** when creating a new local user, or when editing a user who does not have one.
5. Choose access:
   - **Admin access** - full control (equivalent to administrator).
   - **Per-domain matrix** - enable one or more domains, then tick permissions for each.

6. Click **Save User**.

### Remove a user

Use **Revoke** on a row in the delegations list. You cannot revoke your own account while signed in as that user.

## Permission matrix

Each domain grant includes one or more of these permissions:

| Permission | UI tab | What it allows |
| --- | --- | --- |
| `dashboard` | Dashboard | Domain stats and DNS health summary for the selected domain |
| `emails` | Email Accounts | Create, update, and delete mailboxes; set recovery emails; change passwords and quotas |
| `forwarders` | Forwarders | Forwarders, catch-all routing, and domain pointers |
| `spam` | Spam Controls | SpamAssassin score, whitelist, and blacklist |
| `dns` | Domains | DNS health, setup wizard (existing domains), Cloudflare fixes, password-reset portal configuration |

Permissions are **per domain**. A user with `emails` on `a.example.com` and `dns` on `b.example.com` can manage mailboxes only on `a.example.com` and DNS only on `b.example.com`.

### How the UI applies permissions

- The **domain selector** lists only domains delegated to the user (admins see every domain on the MXroute account).
- Sidebar tabs appear only if the user holds the required permission on **at least one** delegated domain (union across domains).
- Within a tab, actions for the **currently selected domain** require the matching permission for that domain. Switching domains can hide controls the user is not allowed to use.
- The **Dashboard** tab is shown if the user has `dashboard` or `dns` on any domain. Stats and DNS health cards require `dashboard` on the active domain.

### Admin-only operations

These remain restricted to administrators even when a delegated user has broad permissions:

| Operation | Why |
| --- | --- |
| Register or delete domains on MXroute | Account-level lifecycle |
| Toggle mail hosting | Affects entire domain delivery |
| **Access Control** and **Audit Logs** | Security and governance |
| System **Settings** (MXroute keys, OIDC, SMTP, Cloudflare) | Global configuration |
| Account quota sidebar and dashboard quota card | Account-wide MXroute limits |
| DNS wizard - register **new** domain on MXroute (step 3) | Creates account resources |

Delegated users with `dns` can still run the wizard for domains already on the account and use Cloudflare DNS tools where configured.

## Data storage

Delegations are stored in SQLite:

- `users` - login identifier, optional `password_hash`, `is_admin`, optional `contact_email`
- `delegations` - `user_id`, `domain`, `permissions` (JSON array)

The session carries `domain_grants` and `delegated_domains` after login. API handlers call `require_permission`, `require_any_permission`, or `require_admin` on each route.

## OIDC and local admin together

A typical production layout:

- **OIDC** for staff admins (`OIDC_ADMIN_USERS` / admin group).
- **Local `ADMIN_USER`** as break-glass access if the IdP is unavailable.
- **Delegated local or OIDC users** for customers or team members who manage only their domains.

See [Configuration - Authentication](configuration.md#authentication) for OIDC variables and [Local admin password](admin-password.md) for the break-glass account.

## Audit trail

Delegation changes are written to the JSON-line audit log (`delegation.update`, `delegation.revoke`). Administrators can review entries under **Audit Logs**.

## Related guides

| Guide | Topic |
| --- | --- |
| [Getting started](getting-started.md) | First deploy and initial login |
| [Configuration](configuration.md) | OIDC and security environment variables |
| [Local admin password](admin-password.md) | Break-glass admin credentials |
| [Password reset](password-reset.md) | Recovery emails and mailbox self-service reset |
| [Reverse proxy](reverse-proxy.md) | Production TLS in front of the app |
| [Testing](testing.md) | Delegation and auth test coverage |
