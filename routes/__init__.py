from .auth import auth_bp
from .domains import domains_bp
from .emails import emails_bp
from .spam import spam_bp
from .cloudflare import cloudflare_bp
from .admin import admin_bp
from .password_reset import password_reset_bp
from .reset_portal import reset_portal_bp

__all__ = [
    "auth_bp",
    "domains_bp",
    "emails_bp",
    "spam_bp",
    "cloudflare_bp",
    "admin_bp",
    "password_reset_bp",
    "reset_portal_bp",
]
