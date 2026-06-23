"""Admin API routes — blueprint facade and route registration."""

from routes.admin_blueprint import admin_bp
from routes.admin_delegations import parse_delegation_grants
from routes.admin_notifications import resolve_apprise_urls_for_test
import routes.admin_settings  # noqa: F401  # registers settings, quota, and logs routes on admin_bp
from services.mxroute import audit
from services.notifications import send_test_notification
from utils.apprise_builder import compile_service_url, validate_apprise_url


__all__ = [
    "admin_bp",
    "audit",
    "compile_service_url",
    "parse_delegation_grants",
    "resolve_apprise_urls_for_test",
    "send_test_notification",
    "validate_apprise_url",
]
