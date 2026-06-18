# Configuration

MXroute Manager reads settings from environment variables (`.env` or container env) and from the **Settings** tab in the UI. Secrets in the UI are stored in SQLite; API keys and OIDC client secrets are **environment-only** and are not written to the database.

Copy `.env.example` to `.env` as a starting point.

## MXroute API

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `MX_SERVER` | Yes | — | MXroute server hostname (e.g. `your_mxroute_email_server`) |
| `MX_USER` | Yes | — | MXroute account username |
| `MX_API_KEY` | Yes | — | MXroute API key |

## Core security

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `SECRET_KEY` | Recommended | — | Flask session signing key. Generate a long random string for production. |
| `FORCE_HTTPS` | No | `false` | Set `true` when serving over HTTPS so session cookies use the `Secure` flag. |

## Authentication

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `OIDC_ENABLED` | No | `true` | Set `false` for local username/password login only. |
| `OIDC_CLIENT_ID` | If OIDC on | — | OIDC client ID |
| `OIDC_CLIENT_SECRET` | If OIDC on | — | OIDC client secret (env only) |
| `OIDC_DISCOVERY_URL` | If OIDC on | — | OpenID Provider discovery URL |
| `OIDC_REDIRECT_URI` | If OIDC on | — | Callback URL (e.g. `https://manager.example.com/oidc/callback`) |
| `OIDC_SCOPES` | No | `openid email profile groups` | Space-separated OIDC scopes |
| `OIDC_ADMIN_USERS` | No | — | Comma-separated emails granted admin access |
| `OIDC_ADMIN_GROUP` | No | `administrators` | Group claim value treated as admin |
| `ADMIN_USER` | No | `admin` | Local admin username |
| `ADMIN_PASSWORD` | Yes* | — | Initial local admin password (hashed in DB on first save; can stay in env) |

\*Required for local login when OIDC is disabled, or as a break-glass admin account when OIDC is enabled.

Most OIDC and MXroute fields can also be edited in **Settings** (except env-only secrets).

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
| `RESET_SMTP_PASSWORD` | If enabled | — | SMTP password (env or saved in Settings) |
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
