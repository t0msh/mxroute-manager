"""Per-domain DMARC policy overrides."""

from datetime import datetime, timezone

from models.db_conn import get_conn
from models.db_settings import get_dmarc_record


def get_domain_dmarc_policy(domain):
    domain = domain.lower().strip()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT dmarc_record FROM domain_dmarc_policies WHERE domain = ?",
            (domain,),
        )
        row = cursor.fetchone()
    if not row or not row[0]:
        return None
    return str(row[0]).strip()


def set_domain_dmarc_policy(domain, dmarc_record):
    domain = domain.lower().strip()
    dmarc_record = dmarc_record.strip()
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO domain_dmarc_policies (domain, dmarc_record, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                dmarc_record = excluded.dmarc_record,
                updated_at = excluded.updated_at
            """,
            (domain, dmarc_record, now),
        )
        conn.commit()
    return True


def clear_domain_dmarc_policy(domain):
    domain = domain.lower().strip()
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM domain_dmarc_policies WHERE domain = ?",
            (domain,),
        )
        conn.commit()


def get_dmarc_record_for_domain(domain):
    custom = get_domain_dmarc_policy(domain)
    if custom:
        return custom
    return get_dmarc_record()


def get_dmarc_health_params(domain):
    custom = get_domain_dmarc_policy(domain)
    default = get_dmarc_record()
    return {
        "expected": custom or default,
        "exact_match": bool(custom),
        "default": default,
        "custom": custom,
    }


def dmarc_check_options(domain):
    params = get_dmarc_health_params(domain)
    return {
        "dmarc_expected": params["expected"],
        "dmarc_exact_match": params["exact_match"],
    }


def dmarc_policy_payload(domain):
    params = get_dmarc_health_params(domain)
    return {
        "custom": bool(params["custom"]),
        "default": params["default"],
        "effective": params["expected"],
        "custom_value": params["custom"],
    }
