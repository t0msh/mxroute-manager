# Reverse proxy

MXroute Manager listens on **port 5000** (HTTP inside the container). In production you should terminate TLS at a reverse proxy and forward traffic to the app.

## Supported reverse proxies

| Proxy | Status | Notes |
| --- | --- | --- |
| [Nginx Proxy Manager](https://nginxproxymanager.com/) | **Supported** | Required for one-click branded reset portal deploy (DNS + TLS automation) |
| Caddy | Planned | - |
| Traefik | Planned | - |
| Raw nginx | Planned | Manual config only for now |

Branded reset portals (`reset.yourdomain.com`) use the NPM API to create proxy hosts and Let's Encrypt certificates (Cloudflare DNS-01). You can still run the main app behind any reverse proxy manually; only the **Deploy Portal** button requires NPM.

## Main app behind NPM

1. Create a proxy host in NPM, e.g. `mxtools.example.com`.
2. **Forward hostname:** IP or hostname of the machine running MXroute Manager.
3. **Forward port:** `5000`
4. **Scheme:** HTTP (TLS terminates at NPM).
5. Enable SSL (Let's Encrypt or custom certificate).
6. Set `FORCE_HTTPS=true` in `.env` when the public URL uses HTTPS.

If OIDC is enabled, set `OIDC_REDIRECT_URI` to your public callback URL (e.g. `https://mxtools.example.com/oidc/callback`).

## Branded reset portals

Configured in **Domains → Password Reset Portal** per domain.

### One-click deploy workflow

1. Choose a subdomain (e.g. `reset`) and optional branding (title, logo, theme).
2. Click **Deploy Portal** - the app saves settings, uploads the logo if provided, creates or updates a proxied Cloudflare CNAME, and registers an NPM proxy host with Let's Encrypt (DNS-01 via Cloudflare).
3. Share the portal URL with mailbox owners on that domain.

**Deploy Portal** requires:

- Cloudflare: `CF_API_TOKEN`, `CF_ACCOUNT_ID`
- NPM: `NPM_API_URL`, `NPM_IDENTITY`, `NPM_SECRET`, `NPM_FORWARD_HOST`, `NPM_FORWARD_PORT`
- `RESET_PORTAL_CNAME_TARGET` - the same public hostname as your main app (or another host that already points at NPM)

Disabling a portal or clicking teardown in the UI removes the CNAME and NPM host when automation is configured.

See [configuration.md](configuration.md#branded-reset-portals) for environment variables and [password-reset.md](password-reset.md#branded-reset-portals) for the end-user and admin workflow.

## Related guides

| Guide | Topic |
| --- | --- |
| [Getting started](getting-started.md) | Production deployment checklist |
| [Configuration](configuration.md) | `FORCE_HTTPS`, `TRUSTED_PROXY_COUNT`, NPM variables |
| [Password reset](password-reset.md) | Branded portal workflow and security |
| [Testing](testing.md) | Portal deploy and routing tests |
