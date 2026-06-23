import os

from models.db_conn import get_conn, get_env_config
from models.db_settings import use_secure_cookies


def _database_file():
    from models import db as db_module

    return db_module.DATABASE_FILE


def build_portal_host(subdomain_prefix, domain):
    return f"{subdomain_prefix.strip().lower()}.{domain.strip().lower()}"


def get_branding_dir():
    return os.path.join(os.path.dirname(os.path.abspath(_database_file())), "branding")


def get_reset_portal_cname_target():
    return (
        (get_env_config("RESET_PORTAL_CNAME_TARGET") or "").strip().lower().rstrip(".")
    )


def _row_to_reset_portal(row):
    if not row:
        return None
    from utils.themes import normalize_theme

    return {
        "domain": row[0],
        "enabled": bool(row[1]),
        "subdomain_prefix": row[2] or "",
        "portal_host": row[3] or "",
        "portal_title": row[4] or "",
        "logo_filename": row[5] or "",
        "portal_theme": normalize_theme(row[6] if len(row) > 6 else None),
    }


def get_reset_portal(domain):
    domain = domain.lower().strip()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT domain, enabled, subdomain_prefix, portal_host, portal_title, logo_filename, portal_theme
            FROM domain_reset_portals WHERE domain = ?
            """,
            (domain,),
        )
        row = cursor.fetchone()
    return _row_to_reset_portal(row)


def get_reset_portal_by_host(host):
    host = host.lower().strip().rstrip(".")
    if not host:
        return None
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT domain, enabled, subdomain_prefix, portal_host, portal_title, logo_filename, portal_theme
            FROM domain_reset_portals
            WHERE portal_host = ? AND enabled = 1
            """,
            (host,),
        )
        row = cursor.fetchone()
    return _row_to_reset_portal(row)


def list_reset_portals():
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT domain, enabled, subdomain_prefix, portal_host, portal_title, logo_filename, portal_theme
            FROM domain_reset_portals ORDER BY domain
            """
        )
        rows = cursor.fetchall()
    return [_row_to_reset_portal(row) for row in rows]


def upsert_reset_portal(
    domain, enabled, subdomain_prefix, portal_title=None, portal_theme=None
):
    from utils.validators import validate_subdomain_prefix
    from utils.themes import normalize_theme

    domain = domain.lower().strip()
    enabled = bool(enabled)
    subdomain_prefix = (subdomain_prefix or "").strip().lower()
    portal_title = (portal_title or "").strip()
    theme = normalize_theme(portal_theme)

    if enabled and not subdomain_prefix:
        return False, "Subdomain prefix is required when the portal is enabled."
    if subdomain_prefix:
        ok, message = validate_subdomain_prefix(subdomain_prefix)
        if not ok:
            return False, message

    portal_host = (
        build_portal_host(subdomain_prefix, domain) if subdomain_prefix else ""
    )

    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO domain_reset_portals
                (domain, enabled, subdomain_prefix, portal_host, portal_title, logo_filename, portal_theme)
            VALUES (?, ?, ?, ?, ?, '', ?)
            ON CONFLICT(domain) DO UPDATE SET
                enabled = excluded.enabled,
                subdomain_prefix = excluded.subdomain_prefix,
                portal_host = excluded.portal_host,
                portal_title = excluded.portal_title,
                portal_theme = excluded.portal_theme
            """,
            (
                domain,
                1 if enabled else 0,
                subdomain_prefix,
                portal_host,
                portal_title,
                theme,
            ),
        )
        conn.commit()
    return True, ""


def set_reset_portal_logo(domain, logo_filename):
    domain = domain.lower().strip()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE domain_reset_portals SET logo_filename = ? WHERE domain = ?",
            (logo_filename, domain),
        )
        updated = cursor.rowcount > 0
        conn.commit()
    return updated


def clear_reset_portal_logo(domain):
    portal = get_reset_portal(domain)
    if not portal or not portal.get("logo_filename"):
        return False
    logo_path = os.path.join(get_branding_dir(), domain, portal["logo_filename"])
    if os.path.isfile(logo_path):
        os.remove(logo_path)
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE domain_reset_portals SET logo_filename = '' WHERE domain = ?",
            (domain.lower().strip(),),
        )
        conn.commit()
    return True


def get_active_reset_portal_for_mailbox_domain(domain):
    portal = get_reset_portal(domain)
    if portal and portal.get("enabled") and portal.get("subdomain_prefix"):
        return portal
    return None


def build_reset_portal_url(domain, token):
    portal = get_active_reset_portal_for_mailbox_domain(domain)
    if not portal:
        return None
    scheme = "https" if use_secure_cookies() else "http"
    host = portal["portal_host"]
    return f"{scheme}://{host}/reset-password?token={token}"
