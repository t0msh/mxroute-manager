# MXroute Manager

MXroute Manager is a self-hosted Flask-based web application designed to simplify email hosting management on the MXroute platform. It integrates directly with **MXroute** for mail service management and **Cloudflare** for automated DNS provisioning (MX, SPF, DKIM, DMARC, and verification records).

Authentication is supported via both OpenID Connect (OIDC) and traditional local credentials (username/password), with fine-grained access control to delegate specific domain management to individual users.

## Formerly MXToolbox

This project was originally named **MXToolbox**. It was renamed to **MXroute Manager** to avoid confusion with [MXToolbox.com](https://mxtoolbox.com), the unrelated DNS and email diagnostics service.

| | Old | New |
|---|---|---|
| **GitHub** | `t0msh/mxtoolbox` | [`t0msh/mxroute-manager`](https://github.com/t0msh/mxroute-manager) |
| **Display name** | mxtoolbox | MXroute Manager |
| **Default database** | `mxtoolbox.db` | `mxroute-manager.db` |
| **Docker service** | `mxtoolbox` | `mxroute-manager` |

GitHub redirects old clone URLs to the new repository automatically. If you cloned before the rename, update your remote:

```bash
git remote set-url origin https://github.com/t0msh/mxroute-manager.git
```

**Upgrading an existing deployment:** your data is unchanged. Keep pointing at your existing database file:

```bash
DATABASE_FILE=/data/mxtoolbox.db
```

The same applies to Docker volumes — an existing `mxtoolbox_data` volume continues to work; only set `DATABASE_FILE` to match the file inside it.

## Why?

This started as a way to easily onboard new users to MXroute email domains I own, and a way to reset email passwords for the people I manage email addresses for without needing to go through the pain of logging into each domain individually at mxRoute. I got carried away with the scope creep and ended up trying to get usage out of all of the possibilities of the mxRoute API. After that I figured I could get it to automatically setup Cloudflare DNS records to go with it.

> [!IMPORTANT]
> This tool is 90% vibe coded. And was done so to fix a particular annoyance I had and to learn some python, javascript and how to use API's. It's probably not the most robust or secure thing in the world. It's targeted to my specific needs and uses case and is not meant for the public, however if you want to use it for your own use case, be my guest. And if you feel generous enough to point out my shortcomings, please do so in the issues tab.

---

## Features

### Core mail management
- **Domain Management**: Register and unregister domains on MXroute.
- **Email Account Management**: Create, update quotas/passwords, suspend, and delete email addresses.
- **Email Forwarders**: Create and delete email aliases/forwarders.
- **Domain Pointers & Catch-All**: Manage alias domains and catch-all routing.
- **Spam Control**: Configure SpamAssassin thresholds, whitelists, and blacklists per domain.

### DNS & Cloudflare
- **Cloudflare Integration**: One-click provisioning of Cloudflare zones and mail DNS records (MX, SPF, DKIM, DMARC, and MXroute verification TXT).
- **DNS Record Reference**: Dashboard panel showing the exact MX, SPF, DKIM, and DMARC records MXroute expects for each domain.
- **Live DNS Health Checks**: Public DNS lookups compared against MXroute expectations — shown in the dashboard and in the header status indicator for the active domain. Checks MX, SPF, DKIM, DMARC, and domain verification TXT.

### Access control & authentication
- **Delegated Access Control**: Administrators assign specific domains (or full admin access) to individual users.
- **OIDC / SSO**: OpenID Connect login with group- and email-based admin promotion.
- **Local Credentials**: Username/password login stored in SQLite, with a configurable fallback admin account.
- **CSRF Protection**: All state-changing API requests require a valid CSRF token.

### Admin settings & UI
- **In-App Settings Panel** (admin only): Configure MXroute, Cloudflare, OIDC, and local admin credentials from the web UI. Values saved here are stored in SQLite and override matching `.env` entries.
- **Workspace Themes**: Six colour schemes (Emerald, Indigo, Crimson, Amber, Amethyst, Cyberpunk) — persisted in the browser via `localStorage`.
- **In-App Confirmations**: Destructive actions use styled modals instead of browser dialogs. Delete operations for mailboxes, forwarders, domains, and delegated users require typing the target email address (or domain name) to confirm.

### Security & observability
- **Secure Cookie Hardening**: `FORCE_HTTPS` enables `Secure` session and CSRF cookies independently of OIDC — required for local-auth deployments behind TLS.
- **Audit Logging**: Admin and user actions are written to daily log files at `logs/YYYY-MM-DD.log` (JSON lines). Passwords are never logged. Covers logins, domain/mailbox changes, delegations, settings updates, and Cloudflare setup.

---

## Quick start

1. Clone the repository and enter the directory:

   ```bash
   git clone https://github.com/t0msh/mxroute-manager.git
   cd mxroute-manager
   ```

2. Copy and edit the environment file:

   ```bash
   cp .env.example .env
   ```

   See [Environment variables](#environment-variables) below for every available option.

3. Run with Docker Compose (recommended) or locally — see [Installation](#installation).

---

## Environment variables

Copy `.env.example` to `.env` and fill in the values you need. Most settings marked **UI** can also be changed later from the **Settings** tab (admin only); values saved in the UI are stored in SQLite and override matching `.env` entries.

### MXroute API

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MX_SERVER` | Yes | — | Hostname of your MXroute server (e.g. `blizzard.mxrouting.net`). **UI** |
| `MX_USER` | Yes | — | Your MXroute administrator username. **UI** |
| `MX_API_KEY` | Yes | — | Your MXroute API key. **UI** |

### Cloudflare

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CF_API_TOKEN` | No | — | Cloudflare API token with `Zone.Zone:Edit` and `Zone.DNS:Edit` permissions. Required for automatic DNS setup. **UI** |
| `CF_ACCOUNT_ID` | No | — | Your Cloudflare account ID. Required for automatic DNS setup. **UI** |

### OpenID Connect (OIDC)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OIDC_ENABLED` | No | `true` | Set to `false` for local username/password login only. **UI** |
| `OIDC_CLIENT_ID` | If OIDC enabled | — | Client ID from your OIDC provider. **UI** |
| `OIDC_CLIENT_SECRET` | If OIDC enabled | — | Client secret from your OIDC provider. **UI** |
| `OIDC_DISCOVERY_URL` | If OIDC enabled | — | Provider discovery URL (e.g. `https://auth.example.com/.well-known/openid-configuration`). **UI** |
| `OIDC_REDIRECT_URI` | If OIDC enabled | — | Callback URL registered with your provider (e.g. `https://your-domain.com/oidc/callback`). **UI** |
| `OIDC_SCOPES` | No | `openid email profile groups` | Space-separated scopes requested from the provider. **UI** |
| `OIDC_ADMIN_USERS` | No | — | Comma-separated email addresses granted super-admin access. **UI** |
| `OIDC_ADMIN_GROUP` | No | `administrators` | OIDC group name that automatically grants admin access. **UI** |

### Local admin & session security

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ADMIN_USER` | No | `admin` | Username for local login. Used as OIDC fallback when enabled, or as the sole login method when OIDC is disabled. **UI** |
| `ADMIN_PASSWORD` | Yes* | — | Password for the local admin account. **UI** |
| `SECRET_KEY` | Recommended | random per restart | Long random string used to sign Flask session cookies. Without this, sessions do not persist across restarts or Gunicorn workers. **Env only** |
| `FORCE_HTTPS` | No | follows OIDC | Set to `true` when served over HTTPS. Enables `Secure` session and CSRF cookies. When unset, secure cookies follow the `OIDC_ENABLED` setting. **Env only** |

\* Required for local login to work (either as fallback or sole method).

### DNS

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DMARC_RECORD` | No | `v=DMARC1; p=none; sp=none; adkim=r; aspf=r;` | TXT value written to `_dmarc` during Cloudflare auto-setup and used for DNS health checks. DMARC is not returned by the MXroute API — see [MXroute's DMARC docs](https://docs.mxroute.com/docs/dns/dmarc.html) before tightening the policy. **Env only** |

### Storage, logging & server

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_FILE` | No | `mxroute-manager.db` | Path to the SQLite database. In Docker, use `/data/mxroute-manager.db`. When upgrading from the old project name, set to your existing file (e.g. `/data/mxtoolbox.db`). **Env only** |
| `LOG_DIR` | No | `./logs` | Directory for daily audit log files (`YYYY-MM-DD.log`). In Docker, use `/data/logs` on the persistent volume. **Env only** |
| `PORT` | No | `5000` | Port the development server listens on (`python app.py` only; Gunicorn in Docker always uses 5000). **Env only** |

---

## Audit Logs

Audit logs are stored outside the SQLite database as one file per day:

```
logs/
  2026-06-16.log
  2026-06-17.log
```

Each line is a JSON object:

```json
{"timestamp": "2026-06-16T10:52:42+00:00", "user": "admin@example.com", "action": "mailbox.delete", "target": "user@domain.com", "details": {}}
```

Logged actions include authentication events, domain and mailbox CRUD, password changes, forwarder/pointer changes, delegation updates, settings changes, and Cloudflare setup runs. Sensitive fields (passwords, API secrets) are excluded from log details.

---

## Installation

### Prerequisites

- **Docker:** Docker Engine and Docker Compose v2, or
- **Local:** Python 3.11+

### Option A — Docker Compose (recommended)

1. Clone and configure:

   ```bash
   git clone https://github.com/t0msh/mxroute-manager.git
   cd mxroute-manager
   cp .env.example .env
   # Edit .env with your settings
   ```

2. Build and start:

   ```bash
   docker compose up --build -d
   ```

3. Open `http://localhost:5000` (or your reverse-proxy URL).

Docker Compose reads configuration from `.env` and persists the database and audit logs in a named volume (`mxroute_manager_data`).

Default `docker-compose.yml`:

```yaml
version: '3.8'

services:
  mxroute-manager:
    build: .
    container_name: mxroute-manager
    restart: always
    ports:
      - "5000:5000"
    env_file:
      - .env
    environment:
      - DATABASE_FILE=/data/mxroute-manager.db
      - LOG_DIR=/data/logs
    volumes:
      - mxroute_manager_data:/data

volumes:
  mxroute_manager_data:
```

**Raw Docker commands** (alternative):

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

> [!IMPORTANT]
> Persist both the SQLite database **and** the audit log directory using a volume. Without this, data and logs are lost when the container is recreated.

### Option B — Local development

1. Clone the repository:

   ```bash
   git clone git@github.com:t0msh/mxroute-manager.git
   cd mxroute-manager
   ```

   Or with HTTPS:

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

4. Configure the environment:

   ```bash
   cp .env.example .env
   # Edit .env — at minimum set MXroute credentials and ADMIN_PASSWORD
   ```

5. Run the application:

   ```bash
   python app.py
   ```

   The app starts on `http://127.0.0.1:5000` by default. Override the port with `PORT=8080 python app.py`.

---

## Production Notes

- Serve behind a reverse proxy (Caddy, nginx, etc.) with TLS enabled, and set `FORCE_HTTPS=true`.
- Generate a strong, unique `SECRET_KEY` before going live.
- The Settings panel can overwrite `.env` values at runtime — for secrets you prefer to keep out of the database, leave them unset in the UI and rely on environment variables only.
- DNS health checks perform live public DNS lookups and require outbound network access from the container/host.
