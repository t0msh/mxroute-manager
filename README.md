# MXroute Manager

[![Tests](https://github.com/t0msh/mxroute-manager/actions/workflows/test.yml/badge.svg)](https://github.com/t0msh/mxroute-manager/actions/workflows/test.yml)

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

| Guide | Description |
| --- | --- |
| [docs/getting-started.md](docs/getting-started.md) | First deploy, UI walkthrough, production checklist |
| [docs/configuration.md](docs/configuration.md) | Environment variables and Settings |
| [docs/admin-password.md](docs/admin-password.md) | Local admin credentials and recovery |
| [docs/access-control.md](docs/access-control.md) | Delegated users and per-domain permissions |
| [docs/password-reset.md](docs/password-reset.md) | Login-page and branded mailbox password reset |
| [docs/reverse-proxy.md](docs/reverse-proxy.md) | TLS and branded reset portals (Nginx Proxy Manager) |
| [docs/testing.md](docs/testing.md) | Test suite layout and how to run it |

## Features

### Mail and domain operations
- Register and remove domains on MXroute
- Provision mailboxes with password, quota, and send-limit controls
- Optional recovery email per mailbox for self-service password reset
- Change password, update limits, and delete mailboxes
- Manage domain pointers and catch-all routing
- Create and remove forwarders
- Configure SpamAssassin threshold, whitelist, and blacklist
- Enable or disable mail hosting for a domain (admin only)

### DNS and Cloudflare workflow
- 3-step Domain & DNS setup wizard with one-click Cloudflare deploy
- DNS health checks for MX, SPF, DKIM, DMARC, and verification records
- Global DNS health status in the UI header

### Branded password-reset portals
- Per-domain reset pages on a subdomain you choose (e.g. `reset.example.com`)
- Logo, title, and theme branding
- One-click **Deploy Portal**: saves settings, uploads logo, and publishes Cloudflare CNAME + [Nginx Proxy Manager](docs/reverse-proxy.md) TLS
- Teardown removes DNS and NPM resources when a portal is disabled

### Access control and authentication
- OIDC/SSO login flow with local credential fallback
- Per-domain permission matrix for delegated users - [docs/access-control.md](docs/access-control.md)
- Self-service mailbox password reset (login page and branded portals) - [docs/password-reset.md](docs/password-reset.md)
- Typed confirmations for destructive operations

### Settings and UX
- In-app Settings for MXroute, OIDC, Cloudflare, SMTP, and local admin
- Theme support (Emerald, Indigo, Crimson, Amber, Amethyst, Cyberpunk, and light variants)
- Client-side API caching with stale-while-revalidate behaviour
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

- [ ] Reverse proxy support beyond Nginx Proxy Manager (Caddy, Traefik, raw nginx)
- [ ] Additional deployment examples (systemd, Kubernetes)

## Related guides

See [docs/README.md](docs/README.md) for the full documentation index, typical setup paths, and links to every guide.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
