"""Authentication routes — blueprint facade and route registration."""

from routes.auth_blueprint import auth_bp
from routes.auth_session import build_session_user, start_user_session
import routes.auth_local  # noqa: F401  # registers /login on auth_bp
import routes.auth_oidc  # noqa: F401  # registers OIDC routes on auth_bp
import routes.auth_profile  # noqa: F401  # registers logout and /api/me routes on auth_bp

__all__ = ["auth_bp", "build_session_user", "start_user_session"]
