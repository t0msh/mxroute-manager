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

MXroute Manager is a self-hosted Flask application for managing MXroute domains, mailboxes, forwarders, DNS setup, delegated access, and branded password-reset portals from a single UI.

## Quickstart

**Requirements:** Docker and Docker Compose, plus MXroute API credentials.

```bash
git clone https://github.com/t0msh/mxroute-manager.git
cd mxroute-manager
cp .env.example .env
```

Edit `.env` — minimum:

```env
MX_SERVER=blizzard.mxrouting.net
MX_USER=your_mxroute_username
MX_API_KEY=your_mxroute_api_key
ADMIN_PASSWORD=choose_a_strong_password
SECRET_KEY=generate_a_long_random_string
```

Start the app:

```bash
docker compose up --build -d
```

Open [http://localhost:5000](http://localhost:5000) and sign in with `admin` and your `ADMIN_PASSWORD`.

For production, put the app behind a reverse proxy with HTTPS. See [docs/reverse-proxy.md](docs/reverse-proxy.md). Full configuration reference: [docs/configuration.md](docs/configuration.md).

### Local development (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit as above
python app.py
```

## Documentation

| Guide | Description |
| --- | --- |
| [docs/configuration.md](docs/configuration.md) | Environment variables and Settings |
| [docs/reverse-proxy.md](docs/reverse-proxy.md) | TLS and branded reset portals (**Nginx Proxy Manager**) |

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
- 3-step Domain & DNS setup wizard with one-click Cloudflare deploy
- DNS health checks for MX, SPF, DKIM, DMARC, and verification records
- Global DNS health status in the UI header

### Branded password-reset portals
- Per-domain reset pages on a subdomain you choose (e.g. `reset.example.com`)
- Logo and title branding
- One-click deploy: Cloudflare CNAME + [Nginx Proxy Manager](docs/reverse-proxy.md) TLS
- Teardown removes DNS and NPM resources when a portal is disabled

### Access control and authentication
- OIDC/SSO login flow with local credential fallback
- Self-service mailbox password reset on the login page (recovery email + SMTP)
- Per-domain permission matrix for delegated users
- Typed confirmations for destructive operations

### Settings and UX
- In-app Settings for MXroute, OIDC, Cloudflare, SMTP, and local admin
- Theme support (Emerald, Indigo, Crimson, Amber, Amethyst, Cyberpunk)
- Client-side API caching with stale-while-revalidate behaviour

### Security and observability
- CSRF protection, secure cookies (`FORCE_HTTPS`), server-side permission checks
- JSON-line audit logs for admin/user actions
- Hashed single-use reset tokens and rate limiting

## Roadmap

- [ ] Reverse proxy support beyond Nginx Proxy Manager (Caddy, Traefik, raw nginx)
- [ ] Additional deployment examples (systemd, Kubernetes)

## Delegated access

Admins configure access in the **Access Control** tab:

| Permission | What it allows |
| --- | --- |
| Dashboard | Overview stats and DNS health |
| Email Accounts | Mailbox management |
| Forwarders | Forwarders, catch-all, and pointers |
| Spam Controls | Spam score, whitelist, and blacklist |
| DNS Records | Domain wizard and Cloudflare DNS fixes |

Mail hosting toggles remain admin-only.

## Mailbox password reset

Mailbox owners reset passwords from the **Reset Mailbox Password** tab on the login page when:

1. A **recovery email** is set on the mailbox
2. **SMTP** is configured in Settings (or env)
3. **Self-Service Reset** is enabled in Settings

Reset requests use generic responses (no mailbox enumeration), rate limits, and single-use hashed tokens. See [docs/configuration.md](docs/configuration.md) for SMTP variables.

## Screenshots

### Dashboard
![Dashboard](screenshots/dashboard.png)

### Domain Management
![Domain Management](screenshots/domain_management.png)

### Email Accounts
![Email Accounts](screenshots/email_accounts.png)

### Forwarders
![Forwarders](screenshots/forwarders.png)

### Spam Controls
![Spam Controls](screenshots/spamcontrol.png)

### Access Control
![Access Control](screenshots/accesscontrol.png)

### Settings
![Settings](screenshots/settings.png)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
