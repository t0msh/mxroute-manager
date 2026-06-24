"""Flask route catalog for the admin API reference page."""

from app_meta import APP_NAME, APP_VERSION


def _auth_note(rule):
    path = rule.rule
    if path in {"/health", "/login", "/logout", "/reset-password"} or path.startswith(
        "/api/public/"
    ):
        return "public"
    if path.startswith("/static/"):
        return "static"
    if path.startswith("/api/admin/api-tokens"):
        return "admin session"
    return "session or Bearer token"


def _tag_for_rule(rule):
    path = rule.rule
    if path.startswith("/api/admin/"):
        return "Admin"
    if path.startswith("/api/public/"):
        return "Public"
    if path.startswith("/api/cloudflare/"):
        return "Cloudflare"
    if "/dns" in path or "/reset-portal" in path:
        return "DNS"
    if "/email" in path or "/forwarders" in path or "/catch-all" in path:
        return "Mail"
    if "/spam" in path:
        return "Spam"
    if path.startswith("/api/domains"):
        return "Domains"
    if path in {"/login", "/logout", "/oidc/callback", "/login/redirect"}:
        return "Auth"
    if path in {"/", "/health", "/api/docs"}:
        return "App"
    return "Other"


def collect_api_routes(app):
    routes = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda item: item.rule):
        if rule.endpoint == "static":
            continue
        methods = sorted(
            method for method in rule.methods if method not in {"HEAD", "OPTIONS"}
        )
        routes.append(
            {
                "path": rule.rule,
                "methods": methods,
                "endpoint": rule.endpoint,
                "auth": _auth_note(rule),
                "tag": _tag_for_rule(rule),
            }
        )
    return routes


def build_openapi_document(app, *, base_url=""):
    paths = {}
    for route in collect_api_routes(app):
        path = route["path"]
        if "<" in path:
            path = path.replace("<", "{").replace(">", "}")
        path_item = paths.setdefault(path, {})
        for method in route["methods"]:
            path_item[method.lower()] = {
                "summary": route["endpoint"],
                "tags": [route["tag"]],
                "description": f"Auth: {route['auth']}",
                "responses": {"200": {"description": "Success"}},
            }

    return {
        "openapi": "3.0.3",
        "info": {
            "title": f"{APP_NAME} API",
            "version": APP_VERSION,
            "description": (
                "Browser clients use session cookies; mutating requests require X-CSRF-Token. "
                "Automation clients may use Authorization: Bearer mxm_<token> (scoped like "
                "delegations; CSRF not required). Admin API token management requires a browser session."
            ),
        },
        "servers": [{"url": base_url or "/"}],
        "paths": paths,
    }
