# MXroute Manager

[![Tests](https://github.com/t0msh/mxroute-manager/actions/workflows/test.yml/badge.svg)](https://github.com/t0msh/mxroute-manager/actions/workflows/test.yml)
[![aislop](https://badges.scanaislop.com/score/t0msh/mxroute-manager.svg)](https://scanaislop.com/t0msh/mxroute-manager)

<p align="center">
  <img src="static/logo-emerald.svg" alt="MXroute Manager logo" width="220" />
</p>

> [!NOTE]
>
> MXroute Manager began as a personal tool to simplify MXroute domain and mailbox management. Most of the codebase was built iteratively with AI-assisted development (Cursor), combined with hands-on work in Python, JavaScript, and third-party APIs.
>
> The project ships with an automated test suite (Python and JavaScript) covering authentication, delegations, DNS idempotency, and reset-portal isolation - without requiring live MXroute, Cloudflare, or NPM credentials in CI. Security-sensitive paths use CSRF protection, rate limiting, hashed credentials, server-side permission checks, and JSON-line audit logging.
>
> Run it on infrastructure you control, back up your SQLite database, and review [Getting started](docs/getting-started.md) before exposing the app to the internet.

MXroute Manager is a self-hosted Flask application for managing MXroute domains, mailboxes, forwarders, DNS setup, delegated access, and branded password-reset portals from a single UI.

## Quickstart

**Requirements:** Docker and Docker Compose, plus MXroute API credentials.

```bash
git clone https://github.com/t0msh/mxroute-manager.git
cd mxroute-manager
cp .env.example .env
# Edit .env - see docs/getting-started.md
docker compose up --build -d
```

Open [http://localhost:5000](http://localhost:5000) and sign in with `admin` (or `ADMIN_USER`) and your `ADMIN_PASSWORD`.

**Full setup walkthrough** (production TLS, Cloudflare, SMTP, portals): [docs/getting-started.md](docs/getting-started.md)

## Documentation

Full index: [docs/README.md](docs/README.md)

### Setup

| Guide | Description |
| --- | --- |
| [docs/getting-started.md](docs/getting-started.md) | First deploy, UI walkthrough, production checklist |
| [docs/configuration.md](docs/configuration.md) | Environment variables and in-app Settings |
| [docs/admin-password.md](docs/admin-password.md) | Local admin credentials and recovery |
| [docs/reverse-proxy.md](docs/reverse-proxy.md) | TLS and branded reset portals (Nginx Proxy Manager) |

### Features

| Guide | Description |
| --- | --- |
| [docs/adding-a-domain.md](docs/adding-a-domain.md) | Domain wizard: verification, MXroute registration, Cloudflare mail DNS |
| [docs/access-control.md](docs/access-control.md) | Delegated users, API tokens, and per-domain permissions |
| [docs/api.md](docs/api.md) | HTTP API, Bearer tokens, and automation examples |
| [docs/password-reset.md](docs/password-reset.md) | Login-page and branded mailbox password reset |
| [docs/notifications.md](docs/notifications.md) | Audit alerts, DNS health monitoring, Apprise delivery |

### UI reference

| Guide | Description |
| --- | --- |
| [docs/app-tour.md](docs/app-tour.md) | Screenshots of every main tab, modals, and reset portal |
| [docs/themes.md](docs/themes.md) | All 10 workspace themes on the login screen |

### Development

| Guide | Description |
| --- | --- |
| [docs/testing.md](docs/testing.md) | Test suite layout and how to run it |
| [docs/frontend-app-scripts.md](docs/frontend-app-scripts.md) | Split `static/js/app/` files and script load order |

## Features

### Mail and domain operations
- Register and remove domains on MXroute
- Provision mailboxes with password, quota, and send-limit controls
- Optional recovery email per mailbox for self-service password reset
- **Client setup** card and modal with IMAP/SMTP/webmail settings after provisioning
- Change password, update limits, and delete mailboxes
- **Active Mailboxes** table with search and pagination (5/10/20 rows per page)
- Manage domain pointers and catch-all routing
- Create and remove forwarders
- Configure SpamAssassin threshold, whitelist, and blacklist
- Enable or disable mail hosting for a domain (admin only)

### DNS and Cloudflare workflow
- 4-step Domain & DNS setup wizard with one-click Cloudflare deploy
- DNS health checks for MX, SPF, DKIM, DMARC, and verification records
- **Fix unhealthy DNS** bulk action for admins
- Optional `webmail.<domain>` CNAME during wizard (checkbox, on by default)
- Global DNS health status in the UI header
- Scheduled DNS health monitoring with Apprise alerts (Notifications tab)

### Automation
- Scoped **API tokens** (`mxm_…`) for scripting without browser sessions - [docs/api.md](docs/api.md)
- In-app **API reference** (`/api/docs`) and OpenAPI skeleton (`/api/openapi.json`)

### Branded password-reset portals
- Per-domain reset pages on a subdomain you choose (e.g. `reset.example.com`)
- Logo, title, and theme branding
- One-click **Deploy Portal**: saves settings, uploads logo, and publishes Cloudflare CNAME + [Nginx Proxy Manager](docs/reverse-proxy.md) TLS
- Teardown removes DNS and NPM resources when a portal is disabled

### Access control and authentication
- OIDC/SSO login flow with local credential fallback
- Per-domain permission matrix for delegated users - [docs/access-control.md](docs/access-control.md)
- API tokens for automation (same scopes as delegations) - [docs/api.md](docs/api.md)
- Self-service mailbox password reset (login page and branded portals) - [docs/password-reset.md](docs/password-reset.md)
- Typed confirmations for destructive operations

### Settings and UX
- In-app Settings for MXroute, OIDC, Cloudflare, SMTP, and local admin
- Link to live API reference from Settings
- Theme support (Emerald, Indigo, Crimson, Amber, Amethyst, Cyberpunk, and light variants)
- Client-side API caching with stale-while-revalidate behaviour
- **Active Domains** table with search and pagination
- Global activity bar and responsive mailbox actions menu

### Security and observability
- CSRF protection, secure cookies (`FORCE_HTTPS`), server-side permission checks
- JSON-line audit logs for admin/user actions
- Hashed single-use reset tokens and rate limiting

## Development

### Local (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

### Running tests

Tests run automatically in [GitHub Actions](.github/workflows/test.yml) on push and PR.

```bash
pip install -r requirements-dev.txt
pytest
```

Coverage:

```bash
pytest --cov=services --cov=models --cov=utils --cov-report=term-missing
```

No live API keys needed - tests use a temp SQLite file and mocked APIs. Details: [docs/testing.md](docs/testing.md).

## Roadmap

- [x] Reverse proxy support beyond Nginx Proxy Manager (Cloudflare Tunnel, Caddy, Traefik, manual docs)
- [x] HTTP API tokens and in-app API reference
- [ ] Additional deployment examples (systemd, Kubernetes)

## Related guides

See [docs/README.md](docs/README.md) for typical setup paths and the same guide list grouped by topic.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
