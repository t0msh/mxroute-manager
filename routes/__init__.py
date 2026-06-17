from .auth import auth_bp
from .domains import domains_bp
from .emails import emails_bp
from .spam import spam_bp
from .cloudflare import cloudflare_bp
from .admin import admin_bp

__all__ = [
    "auth_bp",
    "domains_bp",
    "emails_bp",
    "spam_bp",
    "cloudflare_bp",
    "admin_bp",
]
