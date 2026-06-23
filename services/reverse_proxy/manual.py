from models.db import get_env_config
from services.reverse_proxy.base import BACKEND_MANUAL


def _origin_hint():
    return (get_env_config("MANUAL_PROXY_ORIGIN") or "").strip() or "127.0.0.1:5000"


def manual_snippets(portal_host):
    """Copy-paste reverse-proxy examples for manual setup."""
    portal_host = (portal_host or "").lower().rstrip(".")
    origin = _origin_hint()
    return {
        "origin": origin,
        "nginx": f"""server {{
    listen 443 ssl http2;
    server_name {portal_host};

    # TLS: use certbot DNS-01 or upload a Cloudflare Origin CA cert
    ssl_certificate     /etc/ssl/certs/{portal_host}.pem;
    ssl_certificate_key /etc/ssl/private/{portal_host}.key;

    location / {{
        proxy_pass http://{origin};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}""",
        "caddy": f"""{portal_host} {{
    reverse_proxy {origin}
    tls {{
        dns cloudflare {{env.CF_API_TOKEN}}
    }}
}}""",
        "haproxy": f"""# Frontend (add to your HTTPS frontend)
acl host_{portal_host.replace(".", "_")} hdr(host) -i {portal_host}
use_backend mxroute_portal_{portal_host.replace(".", "_")} if host_{portal_host.replace(".", "_")}

# Backend
backend mxroute_portal_{portal_host.replace(".", "_")}
    server app1 {origin} check""",
        "apache": f"""<VirtualHost *:443>
    ServerName {portal_host}
    SSLEngine on
    SSLCertificateFile /etc/ssl/certs/{portal_host}.pem
    SSLCertificateKeyFile /etc/ssl/private/{portal_host}.key

    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"
    ProxyPass / http://{origin}/
    ProxyPassReverse / http://{origin}/
</VirtualHost>""",
    }


class ManualBackend:
    backend_id = BACKEND_MANUAL
    display_name = "Manual"

    def is_configured(self):
        return False

    def missing_config(self):
        return [
            "REVERSE_PROXY_BACKEND=manual — configure your reverse proxy by hand "
            "(see docs/reverse-proxy.md)"
        ]

    def cname_target(self):
        return None

    def needs_cname_target_env(self):
        return True

    def supports_origin_ca(self):
        return False

    def provision_portal_host(self, portal_host, steps):
        raise ValueError("Manual reverse proxy mode does not support automated deploy")

    def delete_portal_host(self, portal_host, steps=None):
        if steps is not None:
            steps.append("Manual mode: remove the reverse-proxy vhost for this host.")
        return False
