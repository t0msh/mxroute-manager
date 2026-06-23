from services.cf_origin_ca import cf_origin_ca_is_configured, create_origin_certificate
from services.npm import (
    deploy_reset_portal_proxy,
    deploy_reset_portal_proxy_letsencrypt,
    npm_delete_certificate,
    npm_delete_proxy_host,
    npm_is_configured,
)
from services.reverse_proxy.base import BACKEND_NPM


class NpmBackend:
    backend_id = BACKEND_NPM
    display_name = "Nginx Proxy Manager"

    def is_configured(self):
        return npm_is_configured()

    def missing_config(self):
        if npm_is_configured():
            return []
        return [
            "NPM_API_URL, NPM_IDENTITY, NPM_SECRET, NPM_FORWARD_HOST, NPM_FORWARD_PORT"
        ]

    def cname_target(self):
        return None

    def needs_cname_target_env(self):
        return True

    def supports_origin_ca(self):
        return True

    def provision_portal_host(self, portal_host, steps):
        if cf_origin_ca_is_configured():
            try:
                steps.append(
                    f"Issuing Cloudflare Origin CA certificate for {portal_host}..."
                )
                certificate_pem, private_key_pem = create_origin_certificate(portal_host)
                steps.append(f"Origin CA certificate issued for {portal_host}")
                steps.append("Configuring Nginx Proxy Manager proxy host...")
                return deploy_reset_portal_proxy(
                    portal_host, certificate_pem, private_key_pem, steps
                )
            except ValueError as exc:
                steps.append(f"Origin CA skipped: {exc}")

        steps.append(
            f"Provisioning NPM Let's Encrypt certificate for {portal_host} "
            "(Cloudflare DNS challenge)..."
        )
        return deploy_reset_portal_proxy_letsencrypt(portal_host, steps)

    def delete_portal_host(self, portal_host, steps=None):
        npm_delete_proxy_host(portal_host, steps)
        npm_delete_certificate(portal_host, steps)
        return True
