from models.db import get_env_config, get_reset_portal_cname_target

BACKEND_NPM = "npm"
BACKEND_CF_TUNNEL = "cloudflare_tunnel"
BACKEND_CADDY = "caddy"
BACKEND_TRAEFIK = "traefik"
BACKEND_MANUAL = "manual"

_VALID_BACKENDS = {
    BACKEND_NPM,
    BACKEND_CF_TUNNEL,
    BACKEND_CADDY,
    BACKEND_TRAEFIK,
    BACKEND_MANUAL,
}


def get_backend_id():
    raw = (get_env_config("REVERSE_PROXY_BACKEND") or BACKEND_NPM).strip().lower()
    if raw not in _VALID_BACKENDS:
        return BACKEND_NPM
    return raw


def get_backend():
    backend_id = get_backend_id()
    if backend_id == BACKEND_CF_TUNNEL:
        from services.reverse_proxy.cf_tunnel import CfTunnelBackend

        return CfTunnelBackend()
    if backend_id == BACKEND_CADDY:
        from services.reverse_proxy.caddy import CaddyBackend

        return CaddyBackend()
    if backend_id == BACKEND_TRAEFIK:
        from services.reverse_proxy.traefik import TraefikBackend

        return TraefikBackend()
    if backend_id == BACKEND_MANUAL:
        from services.reverse_proxy.manual import ManualBackend

        return ManualBackend()
    from services.reverse_proxy.npm_backend import NpmBackend

    return NpmBackend()


def portal_cname_target():
    backend = get_backend()
    target = backend.cname_target()
    if target:
        return target
    return get_reset_portal_cname_target()


def proxy_is_configured():
    return get_backend().is_configured()


def proxy_missing_config():
    return get_backend().missing_config()
