# Configuration

MXroute Manager reads settings from environment variables (`.env` or container env) and from the **Settings** tab in the UI. Secrets in the UI are stored in SQLite; API keys and OIDC client secrets are **environment-only** and are not written to the database.

Copy `.env.example` to `.env` as a starting point. For a guided first deploy, start with [Getting started](getting-started.md).

## Setup tiers

| Tier | Variables | Enables |
| --- | --- | --- |
| **Minimum** | `MX_*`, `ADMIN_PASSWORD`, `SECRET_KEY` | Local login, mailbox and domain management |
| **Production** | + `FORCE_HTTPS`, `TRUSTED_PROXY_COUNT`, reverse proxy | HTTPS, correct client IP for rate limits |
| **Cloudflare** | + `CF_API_TOKEN`, `CF_ACCOUNT_ID` | DNS wizard, one-click DNS fixes, portal CNAME deploy |
| **Mailbox reset** | + `MAILBOX_RESET_ENABLED`, `RESET_SMTP_*` | Self-service reset on the login page |
| **Branded portals** | + `REVERSE_PROXY_BACKEND`, Cloudflare, backend-specific vars | Per-domain reset pages with one-click **Deploy Portal** |

You can add tiers after the initial install; restart the container when changing `.env`.

## MXroute API

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `MX_SERVER` | Yes | - | MXroute server hostname (e.g. `yourmxserver.mxrouting.net`) |
| `MX_USER` | Yes | - | MXroute account username |
| `MX_API_KEY` | Yes | - | MXroute API key |

## Core security

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `SECRET_KEY` | Recommended | - | Flask session signing key. Generate a long random string for production. |
| `FORCE_HTTPS` | No | `false` | Set `true` when serving over HTTPS so session cookies use the `Secure` flag and HSTS is sent. |
| `TRUSTED_PROXY_COUNT` | No | `1` | Number of trusted reverse proxies in front of the app. Controls how many `X-Forwarded-*` hops are honored for the real client IP (used by login and password-reset rate limiting). Set to `0` if the app is exposed directly with no proxy. |

## Authentication

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `OIDC_ENABLED` | No | `false` | Set `true` to require OIDC/SSO sign-in (configure the OIDC variables below). |
| `OIDC_CLIENT_ID` | If OIDC on | - | OIDC client ID |
| `OIDC_CLIENT_SECRET` | If OIDC on | - | OIDC client secret (env only) |
| `OIDC_DISCOVERY_URL` | If OIDC on | - | OpenID Provider discovery URL |
| `OIDC_REDIRECT_URI` | If OIDC on | - | Callback URL (e.g. `https://manager.example.com/oidc/callback`) |
| `OIDC_SCOPES` | No | `openid email profile groups` | Space-separated OIDC scopes |
| `OIDC_ADMIN_USERS` | No | - | Comma-separated emails granted admin access |
| `OIDC_ADMIN_GROUP` | No | `administrators` | Group claim value treated as admin |
| `ADMIN_USER` | No | `admin` | Local admin username |
| `ADMIN_PASSWORD` | Yes* | - | Initial local admin password (hashed in DB on first save; can stay in env). See [Local admin password](admin-password.md). |
| `ADMIN_PASSWORD_FORCE_SYNC` | No | `false` | One-shot recovery flag - see [Resetting a forgotten password](admin-password.md#resetting-a-forgotten-password). |

\*Required for local login when OIDC is disabled, or as a break-glass admin account when OIDC is enabled.

Most OIDC and MXroute fields can also be edited in **Settings** (except env-only secrets).

> **Local admin password:** `ADMIN_PASSWORD` in `.env` is only hashed on first startup. Changing it later does not update login until you reset the stored hash. Full details: [admin-password.md](admin-password.md).

> **Note:** Settings saved in the UI are cached per worker process. When running multiple Gunicorn workers, a saved change is applied immediately in the worker that handled the save and propagates to other workers as their caches refresh; restart the app if you need every worker to pick up a change instantly.

## Cloudflare

Optional. Powers the Domain & DNS wizard, one-click DNS fixes, and branded reset portal CNAME deployment.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `CF_API_TOKEN` | No | - | Cloudflare API token with DNS edit access (env only) |
| `CF_ACCOUNT_ID` | No | - | Cloudflare account ID |
| `CF_ORIGIN_CA_KEY` | No | - | Cloudflare Origin CA key (env only). Optional; default portal deploy uses NPM Let's Encrypt with DNS challenge via `CF_API_TOKEN`. |

## DNS defaults

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `DMARC_RECORD` | No | `v=DMARC1; p=none; ...` | DMARC TXT value used for Cloudflare auto-setup and health checks |

## Mailbox password reset

Optional self-service reset from the login page and/or branded per-domain portals. Configure in **Settings → Mailbox Password Reset** or via env.

Workflow, security, and portal setup: [password-reset.md](password-reset.md).

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `MAILBOX_RESET_ENABLED` | No | `false` | Enable the login-page reset tab |
| `RESET_SMTP_HOST` | If enabled | - | SMTP server hostname |
| `RESET_SMTP_PORT` | No | `587` | SMTP port |
| `RESET_SMTP_USER` | If enabled | - | SMTP username |
| `RESET_SMTP_PASSWORD` | If enabled | - | SMTP password (**set in `.env` on the server**). If you previously saved this in Settings, add it to `.env` after upgrading - the UI no longer stores SMTP passwords. Until `.env` is set, a legacy value in the database is still used if present. |
| `RESET_SMTP_FROM` | If enabled | - | From address for reset emails |
| `RESET_SMTP_USE_TLS` | No | `true` | Use STARTTLS (`true` / `false`) |

## Branded reset portals

Optional per-domain reset pages (e.g. `reset.example.com`). Requires Cloudflare and a [reverse proxy backend](reverse-proxy.md).

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `REVERSE_PROXY_BACKEND` | No | `npm` | `npm`, `cloudflare_tunnel`, `caddy`, `traefik`, or `manual` |
| `RESET_PORTAL_CNAME_TARGET` | npm/caddy/traefik/manual | - | Public hostname portal subdomains CNAME to (no `https://`) |
| `CF_TUNNEL_ID` | cloudflare_tunnel | - | Remotely managed Cloudflare Tunnel ID |
| `CF_TUNNEL_ORIGIN` | cloudflare_tunnel | - | Origin URL (e.g. `http://127.0.0.1:5000`) |
| `NPM_API_URL` | npm | - | NPM base URL (e.g. `https://npm.example.com`) |
| `NPM_IDENTITY` | npm | - | NPM admin email |
| `NPM_SECRET` | npm | - | NPM admin password (env only) |
| `NPM_FORWARD_HOST` | npm | - | Origin IP/hostname NPM proxies to |
| `NPM_FORWARD_PORT` | npm | `5000` | Origin port |
| `NPM_TLS_VERIFY` | No | `true` | Verify NPM API TLS certificate |
| `NPM_LETSENCRYPT_EMAIL` | No | `NPM_IDENTITY` | Let's Encrypt contact for portal certs |
| `CADDY_ADMIN_URL` | caddy | - | Caddy admin API base URL |
| `CADDY_ADMIN_TOKEN` | No | - | Bearer token if admin API auth is enabled |
| `CADDY_ORIGIN` | caddy | - | Upstream dial address (e.g. `127.0.0.1:5000`) |
| `TRAEFIK_DYNAMIC_DIR` | traefik | - | Directory Traefik file provider watches |
| `TRAEFIK_ORIGIN_URL` | traefik | - | Backend URL (e.g. `http://127.0.0.1:5000`) |
| `TRAEFIK_CERT_RESOLVER` | No | `cloudflare` | Cert resolver name in static Traefik config |
| `MANUAL_PROXY_ORIGIN` | No | `127.0.0.1:5000` | Origin hint shown in manual-mode UI snippets |

Portal branding (subdomain, title, logo) is configured per domain in **Domains → Password Reset Portal**, not via env. See [Password reset - Branded portals](password-reset.md#branded-reset-portals) and [Reverse proxy](reverse-proxy.md#branded-reset-portals).

## Storage and logging

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `DATABASE_FILE` | No | `./mxroute-manager.db` | SQLite database path. Use `/data/mxroute-manager.db` in Docker. |
| `LOG_DIR` | No | `./logs` | Directory for JSON-line audit logs |

## Notifications

See [Notifications](notifications.md) for setup, the in-app builder, audit event subscriptions, and credential storage.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `APPRISE_CRED_NTFY` | No | - | ntfy auth token when stored in `.env` instead of the database |
| `APPRISE_CRED_JSON` | No | - | JSON webhook bearer token |
| `APPRISE_CRED_DISCORD` | No | - | Discord webhook token |
| `APPRISE_CRED_GOTIFY` | No | - | Gotify application token |
| `APPRISE_CRED_PUSHOVER` | No | - | Pushover API token |
| `APPRISE_CRED_TELEGRAM` | No | - | Telegram bot token |
| `APPRISE_CRED_SMTP` | No | - | SMTP password for email notification targets (not needed when using reset SMTP) |

Restart the app after adding or changing any `APPRISE_CRED_*` variable in `.env`.

Event subscriptions and non-secret target URLs are stored in the database via **Notifications** in the UI.

## Development

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `PORT` | No | `5000` | Port for `python app.py` (Gunicorn in Docker always uses 5000) |

## Related guides

| Guide | Topic |
| --- | --- |
| [Getting started](getting-started.md) | First deploy walkthrough |
| [Local admin password](admin-password.md) | Admin credential seeding and recovery |
| [Access control](access-control.md) | OIDC and delegated users |
| [Password reset](password-reset.md) | SMTP and self-service reset variables |
| [Reverse proxy](reverse-proxy.md) | TLS and branded portal variables |
| [Testing](testing.md) | Running the test suite |
