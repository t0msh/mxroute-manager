# Configuration

MXroute Manager reads settings from environment variables (`.env` or container env) and from the **Settings** tab in the UI. Secrets in the UI are stored in SQLite; API keys and OIDC client secrets are **environment-only** and are not written to the database.

Copy `.env.example` to `.env` as a starting point.

## MXroute API

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `MX_SERVER` | Yes | — | MXroute server hostname (e.g. `yourmxserver.mxrouting.net`) |
| `MX_USER` | Yes | — | MXroute account username |
| `MX_API_KEY` | Yes | — | MXroute API key |

## Core security

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `SECRET_KEY` | Recommended | — | Flask session signing key. Generate a long random string for production. |
| `FORCE_HTTPS` | No | `false` | Set `true` when serving over HTTPS so session cookies use the `Secure` flag and HSTS is sent. |
| `TRUSTED_PROXY_COUNT` | No | `1` | Number of trusted reverse proxies in front of the app. Controls how many `X-Forwarded-*` hops are honored for the real client IP (used by login and password-reset rate limiting). Set to `0` if the app is exposed directly with no proxy. |

## Authentication

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `OIDC_ENABLED` | No | `false` | Set `true` to require OIDC/SSO sign-in (configure the OIDC variables below). |
| `OIDC_CLIENT_ID` | If OIDC on | — | OIDC client ID |
| `OIDC_CLIENT_SECRET` | If OIDC on | — | OIDC client secret (env only) |
| `OIDC_DISCOVERY_URL` | If OIDC on | — | OpenID Provider discovery URL |
| `OIDC_REDIRECT_URI` | If OIDC on | — | Callback URL (e.g. `https://manager.example.com/oidc/callback`) |
| `OIDC_SCOPES` | No | `openid email profile groups` | Space-separated OIDC scopes |
| `OIDC_ADMIN_USERS` | No | — | Comma-separated emails granted admin access |
| `OIDC_ADMIN_GROUP` | No | `administrators` | Group claim value treated as admin |
| `ADMIN_USER` | No | `admin` | Local admin username |
| `ADMIN_PASSWORD` | Yes* | — | Initial local admin password (hashed in DB on first save; can stay in env) |
| `ADMIN_PASSWORD_FORCE_SYNC` | No | `false` | Set `true` and restart once to re-apply `ADMIN_PASSWORD` from `.env` when the stored hash is out of date. Remove or set back to `false` afterward. |

\*Required for local login when OIDC is disabled, or as a break-glass admin account when OIDC is enabled.

Most OIDC and MXroute fields can also be edited in **Settings** (except env-only secrets).

### Local admin password: how the database is seeded

On first startup, `init_db()` runs a one-time migration that reads `ADMIN_PASSWORD` from the environment and stores a **bcrypt hash** in SQLite (`ADMIN_PASSWORD_HASH` in the `settings` table). If no admin user exists yet, it also creates a row in `users` for `ADMIN_USER` with that same hash.

After that initial seed:

- Login checks the **stored hash in the database**, not the live `.env` value.
- Editing `ADMIN_PASSWORD` in `.env` and restarting **does not** change the stored hash.
- The plaintext password in `.env` is optional to keep; it is only used for that first seed (or a forced re-sync — see below).

This is intentional: the database is the source of truth for credentials, and `.env` is a bootstrap convenience.

**Sign-in username:** use `ADMIN_USER` (default `admin`). OIDC email addresses (e.g. `you@example.com`) are separate accounts and will not accept the local admin password unless you explicitly gave that user a local password in **Access Control**.

**Docker note:** `docker-compose.yml` sets `DATABASE_FILE=/data/mxroute-manager.db` on a named volume. That file is independent of `mxroute-manager.db` in a dev checkout. Password seeding and resets apply to whichever database the running container actually uses.

**Settings UI:** while signed in as an admin, you can change the local admin password under **Settings → Local Admin Password**. That updates both `ADMIN_PASSWORD_HASH` and the matching `users` row immediately.

### Resetting a forgotten local admin password

Use one of these methods depending on your situation.

#### Option 1 — Re-sync from `.env` (recommended)

Set the new password in `.env`, enable the one-shot flag, and restart the app once:

```env
ADMIN_PASSWORD=your_new_secure_password
ADMIN_PASSWORD_FORCE_SYNC=true
```

After a successful restart, sign in with `ADMIN_USER` and the new password, then remove the flag or set `ADMIN_PASSWORD_FORCE_SYNC=false` so the password cannot be reset from `.env` on every future restart.

For Docker:

```bash
# edit .env, then:
docker compose up -d
```

#### Option 2 — Python one-liner (no flag, same effect)

From the app directory (or inside the container), with the same `DATABASE_FILE` the running app uses:

```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from models.db import set_admin_password_hash
import os
set_admin_password_hash(os.environ['ADMIN_PASSWORD'])
print('Admin password hash updated.')
"
```

Restart is not required for the hash change itself, but restart if you are unsure the app is pointing at the same database file.

Docker example:

```bash
docker compose exec mxroute-manager python3 -c "
from dotenv import load_dotenv; load_dotenv()
from models.db import set_admin_password_hash
import os
set_admin_password_hash(os.environ['ADMIN_PASSWORD'])
print('Admin password hash updated.')
"
```

#### Option 3 — Already signed in

If you still have an admin session (e.g. via OIDC), change the password in **Settings** without touching `.env`.

#### Option 4 — Nuclear reset (last resort)

Deleting the SQLite database (or the Docker volume) and restarting recreates an empty DB and re-seeds from the current `ADMIN_PASSWORD` in `.env`. You will lose delegations, settings saved in the UI, and other local data. Only use this on a fresh install or when you have backups.

> **Note:** Settings saved in the UI are cached per worker process. When running multiple Gunicorn workers, a saved change is applied immediately in the worker that handled the save and propagates to other workers as their caches refresh; restart the app if you need every worker to pick up a change instantly.

## Cloudflare

Optional. Powers the Domain & DNS wizard, one-click DNS fixes, and branded reset portal CNAME deployment.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `CF_API_TOKEN` | No | — | Cloudflare API token with DNS edit access (env only) |
| `CF_ACCOUNT_ID` | No | — | Cloudflare account ID |
| `CF_ORIGIN_CA_KEY` | No | — | Cloudflare Origin CA key (env only). Optional; default portal deploy uses NPM Let's Encrypt with DNS challenge via `CF_API_TOKEN`. |

## DNS defaults

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `DMARC_RECORD` | No | `v=DMARC1; p=none; ...` | DMARC TXT value used for Cloudflare auto-setup and health checks |

## Mailbox password reset

Optional self-service reset from the login page. Configure in **Settings → Mailbox Password Reset** or via env.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `MAILBOX_RESET_ENABLED` | No | `false` | Enable the login-page reset tab |
| `RESET_SMTP_HOST` | If enabled | — | SMTP server hostname |
| `RESET_SMTP_PORT` | No | `587` | SMTP port |
| `RESET_SMTP_USER` | If enabled | — | SMTP username |
| `RESET_SMTP_PASSWORD` | If enabled | — | SMTP password (**set in `.env` on the server**). If you previously saved this in Settings, add it to `.env` after upgrading — the UI no longer stores SMTP passwords. Until `.env` is set, a legacy value in the database is still used if present. |
| `RESET_SMTP_FROM` | If enabled | — | From address for reset emails |
| `RESET_SMTP_USE_TLS` | No | `true` | Use STARTTLS (`true` / `false`) |

## Branded reset portals

Optional per-domain reset pages (e.g. `reset.example.com`). Requires Cloudflare and [Nginx Proxy Manager](reverse-proxy.md).

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `RESET_PORTAL_CNAME_TARGET` | For deploy | — | Public hostname portal subdomains CNAME to (no `https://`) |
| `NPM_API_URL` | For deploy | — | NPM base URL (e.g. `https://npm.example.com`) |
| `NPM_IDENTITY` | For deploy | — | NPM admin email |
| `NPM_SECRET` | For deploy | — | NPM admin password (env only) |
| `NPM_FORWARD_HOST` | For deploy | — | Origin IP/hostname NPM proxies to (your app host) |
| `NPM_FORWARD_PORT` | For deploy | `5000` | Origin port (app listens on 5000 in Docker) |
| `NPM_TLS_VERIFY` | No | `true` | Verify NPM API TLS certificate |
| `NPM_LETSENCRYPT_EMAIL` | No | `NPM_IDENTITY` | Let's Encrypt contact email for portal certs |

Portal branding (subdomain, title, logo) is configured per domain in **Domains → Password Reset Portal**, not via env.

## Storage and logging

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `DATABASE_FILE` | No | `./mxroute-manager.db` | SQLite database path. Use `/data/mxroute-manager.db` in Docker. |
| `LOG_DIR` | No | `./logs` | Directory for JSON-line audit logs |

## Development

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `PORT` | No | `5000` | Port for `python app.py` (Gunicorn in Docker always uses 5000) |
