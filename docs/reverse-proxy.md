# Reverse proxy

MXroute Manager listens on **port 5000** (HTTP inside the container). In production you should terminate TLS at a reverse proxy and forward traffic to the app.

Set `FORCE_HTTPS=true` and `TRUSTED_PROXY_COUNT=1` (or the number of proxies in front of the app) when serving over HTTPS.

## Supported reverse proxies

| Proxy | One-click portal deploy | Notes |
| --- | --- | --- |
| [Nginx Proxy Manager](https://nginxproxymanager.com/) | **Yes** (default) | `REVERSE_PROXY_BACKEND=npm` |
| [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/) | **Yes** | `REVERSE_PROXY_BACKEND=cloudflare_tunnel` — TLS at Cloudflare edge |
| [Caddy](https://caddyserver.com/) | **Yes** | Admin API + DNS ACME via Cloudflare |
| [Traefik](https://traefik.io/) | **Yes** (file provider) | Writes dynamic config fragments; you configure the cert resolver |
| Raw nginx, HAProxy, Apache | Manual | `REVERSE_PROXY_BACKEND=manual` — UI shows copy-paste snippets |
| Pangolin, SWAG, K8s Ingress | Manual | Same as any other proxy: forward to `:5000` and configure portal vhosts by hand |

The **main app** works behind any reverse proxy. **Deploy Portal** (branded reset pages) uses the backend selected by `REVERSE_PROXY_BACKEND`.

## Choose a backend

Set in `.env`:

```bash
REVERSE_PROXY_BACKEND=npm   # default
```

| Value | Extra variables |
| --- | --- |
| `npm` | `NPM_*`, `RESET_PORTAL_CNAME_TARGET` |
| `cloudflare_tunnel` | `CF_TUNNEL_ID`, `CF_TUNNEL_ORIGIN` (no `RESET_PORTAL_CNAME_TARGET`) |
| `caddy` | `CADDY_ADMIN_URL`, `CADDY_ORIGIN`, `RESET_PORTAL_CNAME_TARGET` |
| `traefik` | `TRAEFIK_DYNAMIC_DIR`, `TRAEFIK_ORIGIN_URL`, `RESET_PORTAL_CNAME_TARGET` |
| `manual` | `MANUAL_PROXY_ORIGIN` (optional hint for UI snippets) |

Cloudflare (`CF_API_TOKEN`, `CF_ACCOUNT_ID`) is required for all automated portal deploy modes.

## Main app behind a reverse proxy

### Nginx Proxy Manager

1. Create a proxy host, e.g. `mxtools.example.com`.
2. **Forward hostname:** IP or hostname of the machine running MXroute Manager.
3. **Forward port:** `5000`
4. **Scheme:** HTTP (TLS terminates at NPM).
5. Enable SSL (Let's Encrypt or custom certificate).

### Caddy

```caddy
mxtools.example.com {
    reverse_proxy 127.0.0.1:5000
}
```

### Raw nginx

```nginx
server {
    listen 443 ssl http2;
    server_name mxtools.example.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### HAProxy

```haproxy
frontend https_front
    bind *:443 ssl crt /path/to/cert.pem
    acl host_mxtools hdr(host) -i mxtools.example.com
    use_backend mxroute_app if host_mxtools

backend mxroute_app
    server app1 127.0.0.1:5000 check
```

### Apache httpd

```apache
<VirtualHost *:443>
    ServerName mxtools.example.com
    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"
    ProxyPass / http://127.0.0.1:5000/
    ProxyPassReverse / http://127.0.0.1:5000/
</VirtualHost>
```

If OIDC is enabled, set `OIDC_REDIRECT_URI` to your public callback URL (e.g. `https://mxtools.example.com/oidc/callback`).

## Branded reset portals

Configured in **Domains → Password Reset Portal** per domain.

### One-click deploy workflow

1. Choose a subdomain (e.g. `reset`) and optional branding (title, logo, theme).
2. Click **Deploy Portal** — the app saves settings, creates a proxied Cloudflare CNAME, and configures your selected reverse-proxy backend.
3. Share the portal URL with mailbox owners on that domain.

Disabling a portal removes the CNAME and proxy route when automation is configured.

### Nginx Proxy Manager (default)

- `NPM_API_URL`, `NPM_IDENTITY`, `NPM_SECRET`, `NPM_FORWARD_HOST`, `NPM_FORWARD_PORT`
- `RESET_PORTAL_CNAME_TARGET` — public hostname portal subdomains CNAME to (same as your main app host behind NPM)
- Optional: `CF_ORIGIN_CA_KEY` for Origin CA certs instead of Let's Encrypt DNS-01

### Cloudflare Tunnel

1. Create a remotely managed tunnel (`config_src: cloudflare`) and run `cloudflared` with its token.
2. Set `CF_TUNNEL_ID` and `CF_TUNNEL_ORIGIN` (e.g. `http://127.0.0.1:5000`).
3. Deploy Portal adds an ingress rule for `reset.customer.com` and a proxied CNAME to `{tunnel-id}.cfargotunnel.com`.

TLS terminates at Cloudflare; no local reverse proxy required for portal hostnames.

**Caveats:** `cloudflared` must stay running. Multi-level subdomains may need a Cloudflare Advanced Certificate on some plans.

### Caddy

- `CADDY_ADMIN_URL` (e.g. `http://127.0.0.1:2019`)
- `CADDY_ORIGIN` (e.g. `127.0.0.1:5000`)
- Caddy build must include the Cloudflare DNS plugin for ACME.
- `RESET_PORTAL_CNAME_TARGET` points portal CNAMEs at your public Caddy hostname.

### Traefik (file provider)

1. Enable the [file provider](https://doc.traefik.io/traefik/providers/file/) watching `TRAEFIK_DYNAMIC_DIR`.
2. Configure a `certResolver` with Cloudflare DNS challenge in your static Traefik config.
3. Set `TRAEFIK_ORIGIN_URL` (e.g. `http://127.0.0.1:5000`) and optional `TRAEFIK_CERT_RESOLVER` (default `cloudflare`).

Deploy Portal writes one YAML fragment per portal host; Traefik picks it up automatically.

### Manual mode

Set `REVERSE_PROXY_BACKEND=manual`. Save portal branding in the UI; the **Domains** tab shows nginx, Caddy, HAProxy, and Apache snippets for each portal hostname. Publish the Cloudflare CNAME yourself (`RESET_PORTAL_CNAME_TARGET`).

### Pangolin

[Pangolin](https://docs.pangolin.net/) is a zero-trust access platform (Traefik-backed), not a dumb reverse proxy. Its public HTTP resources require authentication by default. Branded password-reset portals must be **fully public**, so Pangolin is not supported for one-click deploy. Use manual mode or a traditional proxy instead.

## Related guides

| Guide | Topic |
| --- | --- |
| [Getting started](getting-started.md) | Production deployment checklist |
| [Configuration](configuration.md) | `REVERSE_PROXY_BACKEND` and per-backend variables |
| [Password reset](password-reset.md) | Branded portal workflow and security |
| [Testing](testing.md) | Portal deploy and routing tests |
