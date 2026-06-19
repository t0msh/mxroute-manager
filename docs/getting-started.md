# Getting started

This guide walks through a first deployment of MXroute Manager from clone to a working admin session, then points you at optional features (Cloudflare DNS, mailbox self-service reset, branded portals).

## Prerequisites

| Requirement | Notes |
| --- | --- |
| **Docker & Docker Compose** | Recommended for production and the path documented here |
| **MXroute account** | API key from [panel.mxroute.com](https://panel.mxroute.com) → Advanced → API Keys |
| **Public hostname (production)** | Reverse proxy with TLS - see [Reverse proxy](reverse-proxy.md) |

For local development without Docker, see [Development setup](#development-setup-without-docker) below.

## 1. Clone and configure

```bash
git clone https://github.com/t0msh/mxroute-manager.git
cd mxroute-manager
cp .env.example .env
```

Edit `.env` with at least:

```env
MX_SERVER=yourmxserver.mxrouting.net
MX_USER=your_mxroute_username
MX_API_KEY=your_mxroute_api_key
ADMIN_PASSWORD=choose_a_strong_password
SECRET_KEY=generate_a_long_random_string
```

| Variable | Where to find it |
| --- | --- |
| `MX_SERVER` | MXroute panel → API Keys page (mail server hostname) |
| `MX_USER` | Your DirectAdmin / MXroute username |
| `MX_API_KEY` | Create under Advanced → API Keys |
| `SECRET_KEY` | Any long random string (session signing) |
| `ADMIN_PASSWORD` | You choose this - local break-glass admin password |

> **Admin password behaviour:** `ADMIN_PASSWORD` is hashed into SQLite on first startup only. Changing `.env` later does not update login until you reset the stored hash. See [Local admin password](admin-password.md) before you lock yourself out.

Full variable reference: [Configuration](configuration.md).

## 2. Start the application

```bash
docker compose up --build -d
```

The container listens on **port 5000**. Data persists in the `mxroute_manager_data` Docker volume (`/data/mxroute-manager.db` and `/data/logs` inside the container).

Check logs:

```bash
docker compose logs -f mxroute-manager
```

## 3. Sign in

Open [http://localhost:5000](http://localhost:5000) (or your server's IP).

| Field | Value |
| --- | --- |
| Username | `admin` (or your `ADMIN_USER`) |
| Password | The `ADMIN_PASSWORD` you set in `.env` |

Use the **local admin** username - not an OIDC email - unless you have created a separate local user under **Access Control**. See [Access control](access-control.md).

## 4. Initial setup in the UI

After login, work through these in order:

1. **Select a domain** - use the global domain selector at the top. Domains come from your MXroute account.
2. **Dashboard** - confirm DNS health and mail-hosting status for the active domain.
3. **Domains** - run the DNS setup wizard if the domain uses Cloudflare (requires `CF_API_TOKEN` and `CF_ACCOUNT_ID` in `.env` or Settings).
4. **Email Accounts** - provision mailboxes, set recovery emails, manage quotas.
5. **Settings** - review MXroute connectivity, OIDC, SMTP, and security options.

Most non-secret settings can be changed in **Settings** after first boot. API keys and OIDC client secrets remain environment-only.

## 5. Production deployment

Do **not** expose port 5000 directly to the internet without TLS.

1. Put the app behind a reverse proxy (HTTPS termination).
2. Set `FORCE_HTTPS=true` in `.env`.
3. Set `TRUSTED_PROXY_COUNT` to the number of proxies in front of the app (typically `1` for a single NPM or nginx instance).
4. If using OIDC, set `OIDC_REDIRECT_URI` to your public callback URL.

Step-by-step for **Nginx Proxy Manager**: [reverse-proxy.md](reverse-proxy.md).

Redeploy after `.env` changes:

```bash
docker compose up -d
```

## 6. Optional features

### Cloudflare DNS automation

Add to `.env`:

```env
CF_API_TOKEN=your_cloudflare_api_token
CF_ACCOUNT_ID=your_cloudflare_account_id
```

Enables the Domain & DNS wizard, one-click DNS fixes, and CNAME deployment for branded reset portals.

### Mailbox self-service password reset

See [Password reset](password-reset.md) for the login-page flow and requirements. Configure **Settings → Mailbox Password Reset** or the `RESET_SMTP_*` variables in `.env`. Each mailbox needs a **recovery email** set under **Email Accounts**.

### Branded password-reset portals

Per-domain reset pages (e.g. `reset.example.com`) with logo and theme. Requires Cloudflare + [Nginx Proxy Manager](reverse-proxy.md) and the `NPM_*` / `RESET_PORTAL_CNAME_TARGET` variables.

Configure under **Domains → Password Reset Portal**, then click **Deploy Portal** to publish DNS and TLS in one step. Full guide: [Password reset - Branded portals](password-reset.md#branded-reset-portals).

## Post-setup checklist

- [ ] `SECRET_KEY` is unique and not committed to git
- [ ] `FORCE_HTTPS=true` when served over HTTPS
- [ ] SQLite volume backed up (`mxroute_manager_data` or your `DATABASE_FILE` path)
- [ ] OIDC redirect URI matches your public URL (if OIDC enabled)
- [ ] SMTP tested from Settings (if mailbox reset enabled)
- [ ] Delegated users configured - [Access control](access-control.md) (if needed)

## Development setup (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit as above
python app.py
```

Uses `./mxroute-manager.db` in the project directory by default (not the Docker volume).

## Troubleshooting

| Problem | See |
| --- | --- |
| Cannot log in after changing `ADMIN_PASSWORD` in `.env` | [admin-password.md](admin-password.md) |
| DNS wizard greyed out or failing | [configuration.md](configuration.md#cloudflare) - check CF token and account ID |
| Reset portal deploy button missing | NPM and Cloudflare env vars - [configuration.md](configuration.md#branded-reset-portals) |
| Mailbox reset not working | [password-reset.md](password-reset.md) |
| Rate limits or wrong client IP behind proxy | `TRUSTED_PROXY_COUNT` - [configuration.md](configuration.md#core-security) |

## Related guides

| Guide | Topic |
| --- | --- |
| [Configuration](configuration.md) | Every env variable and Settings field |
| [Local admin password](admin-password.md) | Credential seeding and recovery |
| [Access control](access-control.md) | Delegated users and permissions |
| [Password reset](password-reset.md) | Login-page and branded mailbox reset |
| [Reverse proxy](reverse-proxy.md) | TLS, NPM, branded portals |
| [Testing](testing.md) | Running or extending the test suite |
