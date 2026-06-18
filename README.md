# MXroute Manager

<p align="center">
  <img src="static/logo-emerald.svg" alt="MXroute Manager logo" width="220" />
</p>

> [!IMPORTANT]
> 
> This app was 90% vibe coded with Cursor. It was to solve a particular annoyance I personally had with managing the domains I have with email services on MXroute. It was a way for me to learn more about JavaScript, Python and APIs. I got carried away, the AI kept pointing out my failures, and it turned into this.
>
> I fully understand that nobody in their right mind is going to trust this tool to manage their production email environment. This repo is more of a show and tell, in case anyone finds it useful or got annoyed of having to remember their MXroute login to reset their parents' email password.
>
> **Use it at your own risk!**

MXroute Manager is a self-hosted Flask application for managing MXroute domains, mailboxes, forwarders, DNS setup, and delegated access from a single UI.


## Features

### Mail and domain operations
- Register and remove domains on MXroute
- Provision mailboxes with password, quota, and send-limit controls
- Optional recovery email per mailbox for self-service password reset
- Suspend/activate, change password, update limits, and delete mailboxes
- Manage domain pointers and catch-all routing
- Create and remove forwarders
- Configure SpamAssassin threshold, whitelist, and blacklist
- Enable or disable mail hosting for a domain (admin only)

### DNS and Cloudflare workflow
- 3-step Domain & DNS setup wizard
- DNS health checks for MX, SPF, DKIM, DMARC, and verification records
- One-click Cloudflare fixes (single record or fix-all)
- Global DNS health status in the UI header

### Access control and authentication
- OIDC/SSO login flow
- Local credential login fallback
- Self-service mailbox password reset tab on the login page (recovery email + SMTP required)
- Per-domain permission matrix for delegated users (`dashboard`, `emails`, `forwarders`, `spam`, `dns`)
- Grant different functions per domain (for example, spam controls only on one domain)
- Existing delegations keep full access after upgrades
- Typed confirmations for destructive operations

### Settings and UX
- In-app Settings tab for MXroute, OIDC, Cloudflare, and local admin settings
- Mailbox password reset SMTP configuration and test-email sending in Settings
- About box with version, repository link, license, and attributions
- Theme support (Emerald, Indigo, Crimson, Amber, Amethyst, Cyberpunk)
- Client-side API caching with stale-while-revalidate behaviour
- Background refresh with subtle UI indicators while data updates
- Reduced redundant API calls when switching tabs or revisiting sections

### Security and observability
- CSRF protection for state-changing requests
- Configurable secure cookie enforcement (`FORCE_HTTPS`)
- Server-side permission checks on all domain-scoped API routes
- JSON-line audit logs for key admin/user actions
- Self-service password reset with hashed single-use tokens and rate limiting

## Delegated access

Admins configure access in the **Access Control** tab. For each user you can:

1. Grant **Admin** access (full control), or
2. Enable specific domains and choose permissions per domain:

| Permission | What it allows |
| --- | --- |
| Dashboard | Overview stats and DNS health |
| Email Accounts | Mailbox management |
| Forwarders | Forwarders, catch-all, and pointers |
| Spam Controls | Spam score, whitelist, and blacklist |
| DNS Records | View and copy required DNS records |

Delegated users only see nav tabs and actions they are permitted to use. Mail hosting toggles remain admin-only.

Local username accounts (not email-based logins) can have an optional **contact email** in Access Control. This is used for SMTP test emails and other admin notifications when no login email is available.

## Mailbox password reset

Mailbox owners can reset their own password from the **Reset Mailbox Password** tab on the login page. This requires:

1. **Recovery email** — set when provisioning a mailbox (optional) or later via the **Recovery** action in the Email Accounts tab.
2. **SMTP settings** — configured in **Settings → Mailbox Password Reset** (or via environment variables).
3. **Feature enabled** — toggle **Self-Service Reset** to **Enabled** in the same settings section.

Flow:

1. Mailbox owner enters their full mailbox address on the login page reset tab.
2. If a recovery email exists, a one-time link is emailed (valid for 1 hour).
3. The owner sets a new password on the reset page; the app updates the mailbox via the MXRoute API.

Security notes:

- Reset requests always return the same generic message (no mailbox enumeration).
- Rate limits apply per IP and per mailbox.
- Recovery email must differ from the mailbox address.
- Reset tokens are single-use and stored hashed.

### SMTP test emails

Admins can send a test email from **Settings → Mailbox Password Reset** to verify SMTP settings before enabling self-service reset. The test uses the current form values (including an unsaved password if entered).

Test emails are sent to your **notification email**:

- OIDC users and local users who sign in with a real email address use that login email.
- Local username accounts need a **contact email** set in **Access Control** or under **Your Contact Email** in the SMTP settings section.

## Screenshots

### Dashboard
![Dashboard](screenshots/dashboard.png)

### Domain Management
![Domain Management](screenshots/domain_management.png)

### Email Accounts
![Email Accounts](screenshots/email_accounts.png)

### Active Emails
![Active Emails](screenshots/active_emails.png)

### Forwarders
![Forwarders](screenshots/forwarders.png)

### Spam Controls
![Spam Controls](screenshots/spamcontrol.png)

### Access Control
![Access Control](screenshots/accesscontrol.png)

### Settings
![Settings](screenshots/settings.png)


## Installation

### Requirements
- Python 3.11+
- MXroute API credentials (`MX_SERVER`, `MX_USER`, `MX_API_KEY`)
- Optional Cloudflare API credentials for DNS automation

---

### Option A: Run locally

1. Clone and enter the repo:

```bash
git clone https://github.com/t0msh/mxroute-manager.git
cd mxroute-manager
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Configure environment:

```bash
cp .env.example .env
```

Edit `.env` and set at least:
- `MX_SERVER`
- `MX_USER`
- `MX_API_KEY`
- `ADMIN_PASSWORD`
- `SECRET_KEY` (recommended)

5. Start the app:

```bash
python app.py
```

Open: [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

### Option B: Run with Docker Compose

1. Clone and configure:

```bash
git clone https://github.com/t0msh/mxroute-manager.git
cd mxroute-manager
cp .env.example .env
```

2. Build and start:

```bash
docker compose up --build -d
```

3. Open: [http://localhost:5000](http://localhost:5000)

4. Stop:

```bash
docker compose down
```

Data persists in the `mxroute_manager_data` volume (`/data` in container) and includes database and logs.

---

### Option C: Run with plain Docker

```bash
docker build -t mxroute-manager .
docker run -d \
  --name mxroute-manager \
  -p 5000:5000 \
  --env-file .env \
  -e DATABASE_FILE=/data/mxroute-manager.db \
  -e LOG_DIR=/data/logs \
  -v mxroute_manager_data:/data \
  --restart always \
  mxroute-manager
```

## Environment variables (summary)

| Variable | Required | Purpose |
| --- | --- | --- |
| `MX_SERVER` | Yes | MXroute server hostname |
| `MX_USER` | Yes | MXroute username |
| `MX_API_KEY` | Yes | MXroute API key |
| `ADMIN_USER` | No | Local admin username (default: `admin`) |
| `ADMIN_PASSWORD` | Yes (for local login) | Local admin password |
| `OIDC_ENABLED` | No | Enable/disable OIDC login |
| `OIDC_CLIENT_ID` | If OIDC enabled | OIDC client ID |
| `OIDC_CLIENT_SECRET` | If OIDC enabled | OIDC client secret |
| `OIDC_DISCOVERY_URL` | If OIDC enabled | OIDC discovery URL |
| `OIDC_REDIRECT_URI` | If OIDC enabled | OIDC callback URL |
| `OIDC_SCOPES` | No | OIDC scopes |
| `OIDC_ADMIN_USERS` | No | Comma-separated admin emails |
| `OIDC_ADMIN_GROUP` | No | Admin group claim |
| `CF_API_TOKEN` | No | Cloudflare API token |
| `CF_ACCOUNT_ID` | No | Cloudflare account ID |
| `DMARC_RECORD` | No | Default DMARC TXT value |
| `DATABASE_FILE` | No | SQLite database path |
| `LOG_DIR` | No | Audit log directory |
| `SECRET_KEY` | Recommended | Session signing key |
| `FORCE_HTTPS` | No | Force secure cookies |
| `PORT` | No | Local dev server port |
| `MAILBOX_RESET_ENABLED` | No | Enable self-service mailbox password reset |
| `RESET_SMTP_HOST` | If reset enabled | SMTP server for reset emails |
| `RESET_SMTP_PORT` | No | SMTP port (default: `587`) |
| `RESET_SMTP_USER` | If reset enabled | SMTP username |
| `RESET_SMTP_PASSWORD` | If reset enabled | SMTP password |
| `RESET_SMTP_FROM` | If reset enabled | From address for reset emails |
| `RESET_SMTP_USE_TLS` | No | Use STARTTLS (`true`/`false`) |


## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
