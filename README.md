# MXroute Manager

<p align="center">
  <img src="static/logo.svg" alt="MXroute Manager logo" width="220" />
</p>

MXroute Manager is a self-hosted Flask application for managing MXroute domains, mailboxes, forwarders, DNS setup, and delegated access from a single UI.


## Features

### Mail and domain operations
- Register and remove domains on MXroute
- Provision mailboxes with password, quota, and send-limit controls
- Suspend/activate, change password, update limits, and delete mailboxes
- Manage domain pointers and catch-all routing
- Create and remove forwarders
- Configure SpamAssassin threshold, whitelist, and blacklist

### DNS and Cloudflare workflow
- 3-step Domain & DNS setup wizard
- DNS health checks for MX, SPF, DKIM, DMARC, and verification records
- One-click Cloudflare fixes (single record or fix-all)
- Global DNS health status in the UI header

### Access control and authentication
- OIDC/SSO login flow
- Local credential login fallback
- Delegated domain-level access for non-admin users
- Typed confirmations for destructive operations

### Settings and UX
- In-app Settings tab for MXroute, OIDC, Cloudflare, and local admin settings
- About box with version, repository link, license, and attributions
- Theme support (Emerald, Indigo, Crimson, Amber, Amethyst, Cyberpunk)

### Security and observability
- CSRF protection for state-changing requests
- Configurable secure cookie enforcement (`FORCE_HTTPS`)
- JSON-line audit logs for key admin/user actions

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

## Project links
- Repository: [github.com/t0msh/mxroute-manager](https://github.com/t0msh/mxroute-manager)
- License: [MIT](LICENSE)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
