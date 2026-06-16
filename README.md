# MXroute Manager

MXroute Manager is a self-hosted Flask-based web application designed to simplify email hosting management on the MXroute platform. It integrates directly with **MXroute** for mail service management and **Cloudflare** for automated DNS provisioning (MX, SPF, DKIM, DMARC, and verification records).

Authentication is supported via both OpenID Connect (OIDC) and traditional local credentials (username/password), with fine-grained access control to delegate specific domain management to individual users.

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

## Configuration

Copy the example environment file and edit it:

```bash
cp .env.example .env
```

Most settings can also be changed later from the **Settings** tab in the web UI (admin only). UI-saved values are stored in the SQLite database and take precedence over `.env`.

### 1. MXroute Settings
- `MX_SERVER`: The hostname of your MXroute server (e.g., `blizzard.mxrouting.net`).
- `MX_USER`: Your MXroute administrator username.
- `MX_API_KEY`: Your MXroute API key.

### 2. Cloudflare Settings
- `CF_API_TOKEN`: A Cloudflare API Token with permissions to edit DNS records and zones (`Zone.Zone:Edit`, `Zone.DNS:Edit`).
- `CF_ACCOUNT_ID`: Your Cloudflare Account ID.

### 3. DNS & DMARC
- `DMARC_RECORD`: TXT value written to `_dmarc` during Cloudflare auto-setup and used for DNS health checks. Defaults to MXroute's recommended monitor-only policy:
  ```
  v=DMARC1; p=none; sp=none; adkim=r; aspf=r;
  ```
  DMARC is not returned by the MXroute API — this value is configured by you. See [MXroute's DMARC docs](https://docs.mxroute.com/docs/dns/dmarc.html) before tightening the policy.

### 4. Authentication & Security
- `OIDC_ENABLED`: Set to `true` to authenticate via OpenID Connect + local admin fallback, or `false` for local credentials only.
- `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET`: Credentials from your OIDC Identity Provider.
- `OIDC_DISCOVERY_URL`: The discovery document URL (e.g., `https://auth.example.com/.well-known/openid-configuration`).
- `OIDC_REDIRECT_URI`: The callback endpoint (e.g., `https://your-domain.com/oidc/callback`).
- `OIDC_SCOPES`: The authorization scopes requested from the provider (defaults to `openid email profile groups`).
- `OIDC_ADMIN_USERS`: Comma-separated list of emails that should have super-administrator privileges.
- `OIDC_ADMIN_GROUP`: OIDC group name that automatically grants admin privileges (defaults to `administrators`).
- `SECRET_KEY`: A long, random string used by Flask to sign session cookies securely.
- `FORCE_HTTPS`: Set to `true` when the app is served over HTTPS. Enables `Secure` session and CSRF cookies independently of OIDC. When unset, secure cookies follow the OIDC setting.

### 5. Local Fallback Admin
- `ADMIN_USER`: The username for local fallback (defaults to `admin`).
- `ADMIN_PASSWORD`: A secure password for the fallback administrator.

### 6. Storage & Logging
- `DATABASE_FILE`: Path to the SQLite database (defaults to `mxroute-manager.db` in the app directory). In Docker, use `/data/mxroute-manager.db`. If upgrading from the old project name, set this to your existing file (e.g. `/data/mxtoolbox.db`).
- `LOG_DIR`: Directory for daily audit log files (defaults to `./logs`). In Docker, use `/data/logs` on the persistent volume.

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

## How to Run Locally

### Prerequisites
- Python 3.11+

### Installation & Execution
1. Clone the repository:
   * **Using SSH:**
     ```bash
     git clone git@github.com:t0msh/mxroute-manager.git
     cd mxroute-manager
     ```
   * **Using HTTPS:**
     ```bash
     git clone https://github.com/t0msh/mxroute-manager.git
     cd mxroute-manager
     ```
2. Create a Python virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure your environment:
   ```bash
   cp .env.example .env
   # Edit .env with your MXroute, Cloudflare, and auth settings
   ```
5. Run the application:
   ```bash
   python app.py
   ```
   The application will start by default on `http://127.0.0.1:5000`.

---

## Deployment with Docker

The application includes a `Dockerfile` and `docker-compose.yml` for easy containerized deployment.

> [!IMPORTANT]
> Persist both the SQLite database **and** the audit log directory using a volume. Without this, data and logs are lost when the container is recreated.

### Using Docker Compose (Recommended)
Docker Compose reads configuration from `.env` and persists data in a named volume (`mxroute_manager_data`).

1. Configure your `.env` file.
2. Build and start the containers in detached (background) mode:
   ```bash
   docker compose up --build -d
   ```

The default `docker-compose.yml` configuration:
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

### Using Raw Docker Commands
1. Build the Docker image:
   ```bash
   docker build -t mxroute-manager .
   ```
2. Run the container with a persistent volume for the database and logs:
   ```bash
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

---

## Production Notes

- Serve behind a reverse proxy (Caddy, nginx, etc.) with TLS enabled, and set `FORCE_HTTPS=true`.
- Generate a strong, unique `SECRET_KEY` before going live.
- The Settings panel can overwrite `.env` values at runtime — for secrets you prefer to keep out of the database, leave them unset in the UI and rely on environment variables only.
- DNS health checks perform live public DNS lookups and require outbound network access from the container/host.
