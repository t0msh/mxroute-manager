import os
import json
import threading
import secrets
import time
from functools import wraps
from urllib.parse import urlencode

import requests  # type: ignore
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv

from audit_log import write_audit_log
from dns_health import check_dns_health

load_dotenv()

app = Flask(__name__)

# Flask Session security key and session cookies hardening
_secret_key = os.getenv("SECRET_KEY")
if not _secret_key:
    app.logger.warning("SECRET_KEY not set — sessions will not persist across restarts or workers!")
    _secret_key = os.urandom(24).hex()
app.secret_key = _secret_key

# SQLite Persistent Storage configuration (early definition for dynamic configs)
import sqlite3
DATABASE_FILE = os.getenv("DATABASE_FILE", os.path.join(os.path.dirname(__file__), "mxroute-manager.db"))
MAPPING_FILE = os.path.join(os.path.dirname(__file__), "domain_mapping.json")

def get_config_value(key, default=None):
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        if row is not None:
            return row[0]
    except Exception:
        pass
    return os.getenv(key, default)

# Dynamic Configuration Getters
def is_oidc_enabled():
    return get_config_value("OIDC_ENABLED", "true").lower() == "true"

def get_oidc_client_id():
    return get_config_value("OIDC_CLIENT_ID")

def get_oidc_client_secret():
    return get_config_value("OIDC_CLIENT_SECRET")

def get_oidc_discovery_url():
    return get_config_value("OIDC_DISCOVERY_URL")

def get_oidc_redirect_uri():
    return get_config_value("OIDC_REDIRECT_URI")

def get_oidc_scopes():
    return get_config_value("OIDC_SCOPES", "openid email profile groups").strip()

def get_oidc_admin_users():
    admin_users_raw = get_config_value("OIDC_ADMIN_USERS", "")
    return set(email.strip().lower() for email in admin_users_raw.split(",") if email.strip())

def get_oidc_admin_group():
    return get_config_value("OIDC_ADMIN_GROUP", "administrators").strip()

def get_admin_user():
    return get_config_value("ADMIN_USER", "admin").strip().lower()

def get_admin_password():
    return get_config_value("ADMIN_PASSWORD")

def get_dmarc_record():
    default = os.getenv("DMARC_RECORD", "v=DMARC1; p=none; sp=none; adkim=r; aspf=r;")
    return get_config_value("DMARC_RECORD", default).strip()

def use_secure_cookies():
    """Use Secure cookies when FORCE_HTTPS is set, or OIDC is enabled (legacy default)."""
    explicit = os.getenv("FORCE_HTTPS")
    if explicit is not None and explicit.strip() != "":
        return explicit.lower() in ("true", "1", "yes")
    return is_oidc_enabled()

app.config.update(
    SESSION_COOKIE_SECURE=use_secure_cookies(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

import re

# Validation helpers
def validate_domain(domain):
    if not domain or not isinstance(domain, str):
        return False
    pattern = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
    return bool(re.match(pattern, domain))

def validate_username(username):
    if not username or not isinstance(username, str):
        return False
    pattern = r"^[a-zA-Z0-9._-]+$"
    return bool(re.match(pattern, username))

def init_db():
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                is_admin BOOLEAN NOT NULL DEFAULT 0
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delegations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                domain TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, domain)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        conn.commit()

        # Perform migration from JSON if it exists
        if os.path.exists(MAPPING_FILE):
            try:
                with open(MAPPING_FILE, 'r') as f:
                    mapping = json.load(f)
                
                for email, domains in mapping.items():
                    email = email.lower().strip()
                    if not email:
                        continue
                    is_admin = "*" in domains or email in get_oidc_admin_users() or email == get_admin_user() or email == "admin@local"
                    
                    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
                    user_row = cursor.fetchone()
                    if not user_row:
                        cursor.execute(
                            "INSERT INTO users (email, is_admin) VALUES (?, ?)",
                            (email, 1 if is_admin else 0)
                        )
                        user_id = cursor.lastrowid
                    else:
                        user_id = user_row[0]
                    
                    for domain in domains:
                        domain = domain.lower().strip()
                        if domain == "*":
                            continue
                        cursor.execute(
                            "INSERT OR IGNORE INTO delegations (user_id, domain) VALUES (?, ?)",
                            (user_id, domain)
                        )
                conn.commit()
                
                # Rename mapping file to prevent future migrations
                bak_file = MAPPING_FILE + ".bak"
                os.rename(MAPPING_FILE, bak_file)
                app.logger.info(f"Successfully migrated {MAPPING_FILE} to SQLite and renamed to {bak_file}")
            except Exception as e:
                app.logger.error(f"Failed to migrate legacy mapping file: {e}")
 
        # Seed initial admin user if empty and ADMIN_PASSWORD is set
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        admin_count = cursor.fetchone()[0]
        if admin_count == 0 and get_admin_password():
            from werkzeug.security import generate_password_hash
            admin_email = get_admin_user().lower().strip()
            hashed_password = generate_password_hash(get_admin_password())
            cursor.execute(
                "INSERT OR IGNORE INTO users (email, password_hash, is_admin) VALUES (?, ?, 1)",
                (admin_email, hashed_password)
            )
            conn.commit()
            app.logger.info(f"Seeded initial admin user '{admin_email}' into SQLite database.")
        conn.close()
    except Exception as e:
        app.logger.error(f"Failed to initialize database: {e}")

# Run database initialization
init_db()

def load_domain_mapping():
    mapping = {}
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.email, u.is_admin, d.domain 
            FROM users u 
            LEFT JOIN delegations d ON u.id = d.user_id
        """)
        rows = cursor.fetchall()
        conn.close()
        
        for email, is_admin, domain in rows:
            email = email.lower()
            if email not in mapping:
                mapping[email] = []
            if is_admin and "*" not in mapping[email]:
                mapping[email].append("*")
            if domain and domain.lower() not in mapping[email]:
                mapping[email].append(domain.lower())
    except Exception as e:
        app.logger.error(f"Error loading domain mapping from SQLite: {e}")
    return mapping

# Lazy OIDC provider configuration fetch — thread-safe with TTL
_oidc_config = None
_oidc_config_fetched_at = 0.0
_oidc_config_lock = threading.Lock()
_OIDC_CONFIG_TTL = 3600  # Re-fetch the discovery document after 1 hour

def get_oidc_config():
    global _oidc_config, _oidc_config_fetched_at
    now = time.monotonic()
    # Fast path: cached config is still fresh — no lock needed for a pure read
    if _oidc_config is not None and (now - _oidc_config_fetched_at) < _OIDC_CONFIG_TTL:
        return _oidc_config
    discovery_url = get_oidc_discovery_url()
    if not discovery_url:
        raise ValueError("OIDC_DISCOVERY_URL is not configured")
    with _oidc_config_lock:
        # Double-check inside the lock in case another thread already refreshed
        now = time.monotonic()
        if _oidc_config is not None and (now - _oidc_config_fetched_at) < _OIDC_CONFIG_TTL:
            return _oidc_config
        try:
            res = requests.get(discovery_url, timeout=10)
            res.raise_for_status()
            _oidc_config = res.json()
            _oidc_config_fetched_at = time.monotonic()
            return _oidc_config
        except Exception as e:
            app.logger.error(f"Failed to fetch OIDC configuration: {e}")
            raise

# Active user and permission contexts
def get_current_user():
    return session.get("user")

def audit(action, target="", **details):
    user = get_current_user()
    email = (user or {}).get("email", "system")
    write_audit_log(action, email, target, details or None)

def is_user_admin(user):
    if not user:
        return False
    email_val = user.get("email")
    email = email_val.lower() if isinstance(email_val, str) else ""
    if email in get_oidc_admin_users() or email == get_admin_user() or email == "admin@local":
        return True
    mapping = load_domain_mapping()
    if "*" in mapping.get(email, []):
        return True
    return user.get("is_admin", False)

def has_domain_access(user, domain):
    if not user:
        return False
    if is_user_admin(user):
        return True
    email_val = user.get("email")
    email = email_val.lower() if isinstance(email_val, str) else ""
    mapping = load_domain_mapping()
    return domain.lower() in [d.lower() for d in mapping.get(email, [])]

def require_compat_domain_access(domain):
    """Enforce domain access on backward-compat form routes."""
    user = get_current_user()
    if not user or not has_domain_access(user, domain):
        return jsonify({"success": False, "error": {"message": f"Forbidden: You do not have access to domain '{domain}'"}}), 403
    return None

# Decorators to enforce authorization constraints
def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or not is_user_admin(user):
            return jsonify({"success": False, "error": {"message": "Forbidden: Admin access required"}}), 403
        return f(*args, **kwargs)
    return decorated_function

def require_domain_access(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        domain = kwargs.get('domain')
        if domain:
            if not validate_domain(domain):
                return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
            user = get_current_user()
            if not user or not has_domain_access(user, domain):
                return jsonify({"success": False, "error": {"message": f"Forbidden: You do not have access to domain '{domain}'"}}), 403
        return f(*args, **kwargs)
    return decorated_function

# Route interceptor to enforce login globally
@app.before_request
def check_authentication():
    # Exclude asset paths, authentication logic endpoints
    if request.path.startswith('/static/') or request.path in ['/login', '/login/redirect', '/oidc/callback', '/logout']:
        return
        
    user = session.get('user')
    if not user:
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "error": {"message": "Unauthorized"}}), 401
        return redirect(url_for('login_page'))

# CSRF protection implementation
@app.before_request
def generate_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

@app.context_processor
def inject_global_vars():
    return dict(csrf_token=session.get("csrf_token"), oidc_enabled=is_oidc_enabled())

@app.after_request
def set_csrf_cookie(response):
    if "csrf_token" in session:
        response.set_cookie("csrf_token", session["csrf_token"], samesite="Lax", secure=use_secure_cookies())
    return response

@app.before_request
def csrf_protect():
    # Only protect state-changing methods
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        # Exclude specific paths like login endpoints
        if request.path in ["/login", "/oidc/callback"]:
            return
        
        token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        expected_token = session.get("csrf_token")
        
        if not expected_token or not token or not secrets.compare_digest(expected_token, token):
            return jsonify({"success": False, "error": {"message": "Bad Request: CSRF token missing or invalid"}}), 400


BASE_URL = "https://api.mxroute.com"

def get_mx_headers():
    return {
        "X-Server": get_config_value("MX_SERVER"),
        "X-Username": get_config_value("MX_USER"),
        "X-API-Key": get_config_value("MX_API_KEY"),
        "Content-Type": "application/json"
    }

def mx_request_raw(method, path, payload=None):
    url = f"{BASE_URL}{path}"
    headers = get_mx_headers()
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            response = requests.post(url, json=payload, headers=headers, timeout=30)
        elif method == "PATCH":
            response = requests.patch(url, json=payload, headers=headers, timeout=30)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, timeout=30)
        else:
            return {"success": False, "error": {"message": "Invalid method"}}, 400

        # Handle 204 No Content or empty responses
        if response.status_code == 204 or (not response.text.strip()):
            return {"success": True}, response.status_code

        try:
            return response.json(), response.status_code
        except ValueError:
            return {"success": False, "error": {"message": response.text}}, response.status_code

    except requests.exceptions.RequestException as e:
        return {"success": False, "error": {"message": str(e)}}, 500

def mx_request(method, path, payload=None):
    res, status = mx_request_raw(method, path, payload)
    return jsonify(res), status


def audited_mx(method, path, payload, action, target=""):
    res, status = mx_request_raw(method, path, payload)
    if status in (200, 201, 204) and (not isinstance(res, dict) or res.get("success", True)):
        details = {}
        if isinstance(payload, dict):
            details = {
                key: value for key, value in payload.items()
                if "password" not in key.lower()
            }
        audit(action, target=target or path, **details)
    return jsonify(res), status


def cf_request(method, path, payload=None):
    cf_token = get_config_value("CF_API_TOKEN")
    if not cf_token:
        raise ValueError("Cloudflare API token not configured")

    url = f"https://api.cloudflare.com/client/v4{path}"
    headers = {
        "Authorization": f"Bearer {cf_token}",
        "Content-Type": "application/json"
    }

    response = None
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            response = requests.post(url, json=payload, headers=headers, timeout=30)
        else:
            raise ValueError("Unsupported Cloudflare method")

        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        status = response.status_code if response is not None else "unknown"
        body = response.text[:200] if response is not None else ""
        app.logger.error(f"Cloudflare HTTP error {status}: {body}")
        try:
            # Cloudflare error bodies are structured JSON — return them so callers can inspect .get("success")
            return response.json()  # type: ignore[union-attr]
        except (ValueError, AttributeError):
            raise ValueError(f"Cloudflare request failed ({status}): {body}") from e
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Cloudflare request failed: {e}")
        raise


MAIL_DNS_RECORD_TYPES = ("mx", "spf", "dkim", "dmarc")
DNS_RECORD_TYPES = ("verification",) + MAIL_DNS_RECORD_TYPES

PENDING_MAIL_CHECK = {
    "status": "pending",
    "label": "",
    "message": "MXroute provides this record after the domain is registered (Step 3).",
}


def cf_is_configured():
    return bool(get_config_value("CF_API_TOKEN") and get_config_value("CF_ACCOUNT_ID"))


def domain_on_mxroute(domain):
    domains_list_res, domains_status = mx_request_raw("GET", "/domains")
    if domains_status != 200:
        return False
    domain_lower = domain.lower()
    return any(d.lower() == domain_lower for d in domains_list_res.get("data", []))


def get_mxroute_verification_record():
    verify_res, verify_status = mx_request_raw("GET", "/verification-key")
    if verify_status != 200:
        return None
    return verify_res.get("data", {}).get("record")


def get_mxroute_dns_data(domain):
    mx_dns_res, mx_dns_status = mx_request_raw("GET", f"/domains/{domain}/dns")
    if mx_dns_status != 200:
        return None
    data = mx_dns_res.get("data") or {}
    data["dmarc"] = {"name": "_dmarc", "value": get_dmarc_record()}
    return data


def build_setup_health(domain):
    """DNS health for the setup wizard; supports domains not yet on MXroute."""
    domain = domain.lower().strip()
    on_mxroute = domain_on_mxroute(domain)
    verification_record = get_mxroute_verification_record()

    if on_mxroute:
        mx_dns_data = get_mxroute_dns_data(domain)
        if not mx_dns_data:
            return None
        health = check_dns_health(
            domain,
            mx_dns_data,
            verification_record=verification_record,
            dmarc_expected=get_dmarc_record(),
        )
    else:
        health = {
            "domain": domain,
            "overall": "degraded",
            "checks": {},
        }
        if verification_record:
            partial = check_dns_health(
                domain,
                {},
                verification_record=verification_record,
                dmarc_expected=get_dmarc_record(),
            )
            health["checks"]["verification"] = partial["checks"]["verification"]
        mail_labels = {
            "mx": "MX Records",
            "spf": "SPF (TXT)",
            "dkim": "DKIM (TXT)",
            "dmarc": "DMARC (TXT)",
        }
        for key, label in mail_labels.items():
            check = dict(PENDING_MAIL_CHECK)
            check["label"] = label
            if key == "dkim":
                check["message"] = (
                    "DKIM keys are generated by MXroute when the domain is registered. "
                    "Complete Step 3, then return here to add the record."
                )
            health["checks"][key] = check

        statuses = [c["status"] for c in health["checks"].values()]
        if any(s == "fail" for s in statuses):
            health["overall"] = "unhealthy"
        elif any(s in ("warn", "pending") for s in statuses):
            health["overall"] = "degraded"
        else:
            health["overall"] = "healthy"

    health["on_mxroute"] = on_mxroute
    health["cf_configured"] = cf_is_configured()
    _, mx_status = mx_request_raw("GET", "/domains")
    health["mxroute_reachable"] = mx_status == 200
    return health


def ensure_cf_zone(domain, steps=None):
    cf_account = get_config_value("CF_ACCOUNT_ID")
    if steps is not None:
        steps.append("Querying Cloudflare for existing Zone...")
    zone_search = cf_request("GET", f"/zones?name={domain}")
    if zone_search.get("success") and zone_search.get("result"):
        zone_id = zone_search["result"][0]["id"]
        if steps is not None:
            steps.append(f"Found existing Cloudflare Zone (ID: {zone_id})")
        return zone_id

    if steps is not None:
        steps.append("Creating new Cloudflare Zone...")
    zone_create = cf_request("POST", "/zones", {
        "name": domain,
        "account": {"id": cf_account},
        "jump_start": True,
    })
    if not zone_create.get("success"):
        err_msg = zone_create.get("errors", [{}])[0].get("message", "Unknown Cloudflare error")
        raise ValueError(f"Cloudflare Zone creation failed: {err_msg}")
    zone_id = zone_create["result"]["id"]
    if steps is not None:
        steps.append(f"Created new Cloudflare Zone (ID: {zone_id})")
    return zone_id


def fetch_cf_dns_sets(zone_id):
    cf_dns_search = cf_request("GET", f"/zones/{zone_id}/dns_records?per_page=100")
    existing_records = cf_dns_search.get("result", []) if cf_dns_search.get("success") else []
    existing_mx = set()
    existing_txt = set()
    for rec in existing_records:
        rtype = rec.get("type")
        rname = rec.get("name", "").lower().rstrip(".")
        rcontent = rec.get("content", "").strip('"')
        if rtype == "MX":
            existing_mx.add((rname, rcontent.lower(), rec.get("priority")))
        elif rtype == "TXT":
            existing_txt.add((rname, rcontent))
    return existing_mx, existing_txt


def deploy_dns_record_to_cf(domain, zone_id, record_type, mx_dns_data, verification_record, existing_mx, existing_txt, steps=None):
    """Deploy a single DNS record type to Cloudflare. Returns 'added' or 'skipped'."""
    domain_lower = domain.lower()

    if record_type == "verification":
        if not verification_record:
            raise ValueError("Failed to get verification key from MXroute")
        verify_name = verification_record.get("name")
        verify_value = verification_record.get("value")
        verify_name_full = f"{verify_name}.{domain}".lower()
        has_verify = any(
            rname == verify_name_full and rcontent == verify_value
            for rname, rcontent in existing_txt
        )
        if has_verify:
            if steps is not None:
                steps.append("Verification TXT record already exists in Cloudflare")
            return "skipped"
        verify_dns_add = cf_request("POST", f"/zones/{zone_id}/dns_records", {
            "type": "TXT",
            "name": verify_name,
            "content": verify_value,
            "ttl": 3600,
        })
        if not verify_dns_add.get("success"):
            err_msg = verify_dns_add.get("errors", [{}])[0].get("message", "Unknown Cloudflare error")
            raise ValueError(f"Failed to add verification TXT: {err_msg}")
        existing_txt.add((verify_name_full, verify_value))
        if steps is not None:
            steps.append("Verification TXT record deployed successfully")
        return "added"

    if record_type not in MAIL_DNS_RECORD_TYPES:
        raise ValueError(f"Unknown record type: {record_type}")

    if not mx_dns_data:
        raise ValueError("Mail DNS records require the domain to be registered on MXroute first")

    if record_type == "mx" and mx_dns_data.get("mx_records"):
        added = False
        for mx in mx_dns_data["mx_records"]:
            mx_host = mx["hostname"].lower().rstrip(".")
            mx_priority = mx["priority"]
            has_mx = any(
                rname == domain_lower and rcontent == mx_host
                and int(rpriority or 0) == int(mx_priority or 0)
                for rname, rcontent, rpriority in existing_mx
            )
            if not has_mx:
                cf_request("POST", f"/zones/{zone_id}/dns_records", {
                    "type": "MX",
                    "name": "@",
                    "content": mx["hostname"],
                    "priority": mx["priority"],
                    "ttl": 3600,
                })
                added = True
        if steps is not None:
            steps.append("MX records configured" if added else "MX records already exist (skipping)")
        return "added" if added else "skipped"

    if record_type == "spf" and mx_dns_data.get("spf"):
        spf_val = mx_dns_data["spf"]["value"]
        has_spf = any(
            rname == domain_lower and rcontent.startswith("v=spf1")
            for rname, rcontent in existing_txt
        )
        if has_spf:
            if steps is not None:
                steps.append("SPF record exists (skipping)")
            return "skipped"
        cf_request("POST", f"/zones/{zone_id}/dns_records", {
            "type": "TXT",
            "name": "@",
            "content": spf_val,
            "ttl": 3600,
        })
        if steps is not None:
            steps.append("SPF record configured")
        return "added"

    if record_type == "dkim" and mx_dns_data.get("dkim"):
        dkim_name = mx_dns_data["dkim"]["name"]
        dkim_val = mx_dns_data["dkim"]["value"]
        dkim_host_part = dkim_name.replace(f".{domain}", "")
        dkim_name_full = f"{dkim_host_part}.{domain}".lower()
        has_dkim = any(rname == dkim_name_full for rname, _ in existing_txt)
        if has_dkim:
            if steps is not None:
                steps.append("DKIM record exists (skipping)")
            return "skipped"
        cf_request("POST", f"/zones/{zone_id}/dns_records", {
            "type": "TXT",
            "name": dkim_host_part,
            "content": dkim_val,
            "ttl": 3600,
        })
        if steps is not None:
            steps.append("DKIM record configured")
        return "added"

    if record_type == "dmarc":
        dmarc_val = get_dmarc_record()
        dmarc_name_full = f"_dmarc.{domain}".lower()
        has_dmarc = any(
            rname == dmarc_name_full and "v=dmarc1" in rcontent.replace(" ", "").lower()
            for rname, rcontent in existing_txt
        )
        if has_dmarc:
            if steps is not None:
                steps.append("DMARC record exists (skipping)")
            return "skipped"
        cf_request("POST", f"/zones/{zone_id}/dns_records", {
            "type": "TXT",
            "name": "_dmarc",
            "content": dmarc_val,
            "ttl": 3600,
        })
        existing_txt.add((dmarc_name_full, dmarc_val))
        if steps is not None:
            steps.append("DMARC record configured")
        return "added"

    if steps is not None:
        steps.append(f"No {record_type.upper()} data available from MXroute (skipping)")
    return "skipped"


def register_domain_on_mxroute(domain, steps=None):
    if domain_on_mxroute(domain):
        if steps is not None:
            steps.append("Domain already registered on MXroute")
        return "skipped"
    mx_domain_add, mx_add_status = mx_request_raw("POST", "/domains", {"domain": domain})
    if mx_add_status not in [200, 201]:
        err_msg = mx_domain_add.get("error", {}).get("message", "Unknown error")
        raise ValueError(f"Failed to register domain with MXroute: {err_msg}")
    if steps is not None:
        steps.append("Domain registered on MXroute successfully")
    audit("domain.create", target=domain)
    return "added"


def deploy_missing_dns_to_cf(domain, record_types=None):
    """Fix missing DNS records in Cloudflare for a domain."""
    steps = []
    if not cf_is_configured():
        raise ValueError("Cloudflare credentials not configured")

    health = build_setup_health(domain)
    if not health:
        raise ValueError("Failed to build DNS health state")

    if record_types is None:
        record_types = [
            key for key, check in health["checks"].items()
            if check["status"] in ("warn", "fail")
        ]
    else:
        record_types = [r.lower() for r in record_types]

    mail_requested = [r for r in record_types if r in MAIL_DNS_RECORD_TYPES]
    if mail_requested and not health["on_mxroute"]:
        raise ValueError(
            "MX, SPF, DKIM, and DMARC records require the domain to be registered on MXroute first. "
            "Complete Step 3, then return to Step 2."
        )

    if not record_types:
        return {"fixed": [], "skipped": list(health["checks"].keys()), "steps": ["All DNS records already look good"]}

    steps.append("Fetching existing DNS records from Cloudflare...")
    zone_id = ensure_cf_zone(domain, steps)
    existing_mx, existing_txt = fetch_cf_dns_sets(zone_id)

    verification_record = get_mxroute_verification_record()
    mx_dns_data = get_mxroute_dns_data(domain) if health["on_mxroute"] else None

    fixed = []
    skipped = []
    for record_type in record_types:
        if record_type not in DNS_RECORD_TYPES:
            continue
        check = health["checks"].get(record_type, {})
        if check.get("status") == "pass":
            skipped.append(record_type)
            continue
        if check.get("status") == "pending":
            skipped.append(record_type)
            continue
        result = deploy_dns_record_to_cf(
            domain, zone_id, record_type, mx_dns_data, verification_record,
            existing_mx, existing_txt, steps,
        )
        if result == "added":
            fixed.append(record_type)
        else:
            skipped.append(record_type)

    if fixed:
        audit("dns.fix", target=domain, records=fixed)
    return {"fixed": fixed, "skipped": skipped, "steps": steps}

# --- OIDC AUTHENTICATION ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if session.get("user"):
        return redirect(url_for('home'))
    
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        
        # Check SQLite database first
        user_row = None
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT id, email, password_hash, is_admin FROM users WHERE email = ?", (username,))
            user_row = cursor.fetchone()
            conn.close()
        except Exception as e:
            app.logger.error(f"Error checking user in SQLite: {e}")
            
        if user_row and user_row[2]: # password_hash exists
            from werkzeug.security import check_password_hash
            if check_password_hash(user_row[2], password):
                session["user"] = {
                    "email": user_row[1],
                    "is_admin": bool(user_row[3]),
                    "delegated_domains": load_domain_mapping().get(user_row[1], [])
                }
                write_audit_log("auth.login", user_row[1], user_row[1])
                return redirect(url_for('home'))
        
        # Fallback to local admin config check
        if get_admin_password() and username == get_admin_user() and secrets.compare_digest(password, get_admin_password()):
            session["user"] = {
                "email": username,
                "is_admin": True,
                "delegated_domains": []
            }
            write_audit_log("auth.login", username, username)
            return redirect(url_for('home'))
            
        write_audit_log("auth.login_failed", username, username, {"reason": "invalid_credentials"})
        error = "Invalid credentials. Please try again."
            
    return render_template('login.html', error=error)

@app.route('/login/redirect')
def login_redirect():
    if not is_oidc_enabled():
        return redirect(url_for('home'))
    try:
        config = get_oidc_config()
    except Exception as e:
        return f"Error: OIDC provider configuration failed: {e}", 500
        
    auth_endpoint = config.get("authorization_endpoint")
    if not auth_endpoint:
        return "Error: OIDC provider configuration does not define authorization_endpoint", 500
        
    # Prevent CSRF
    state = secrets.token_urlsafe(16)
    session["oidc_state"] = state
    
    params = {
        "client_id": get_oidc_client_id(),
        "response_type": "code",
        "scope": get_oidc_scopes(),
        "redirect_uri": get_oidc_redirect_uri(),
        "state": state
    }
    
    auth_url = f"{auth_endpoint}?{urlencode(params)}"
    return redirect(auth_url)

@app.route('/oidc/callback')
def oidc_callback():
    if not is_oidc_enabled():
        return redirect(url_for('home'))
        
    state = request.args.get('state')
    expected_state = session.pop("oidc_state", None)
    if not state or not expected_state or not secrets.compare_digest(state, expected_state):
        return "Authentication error: CSRF state verification failed", 400
        
    code = request.args.get('code')
    if not code:
        return "Authentication error: Missing authorization code", 400
        
    try:
        config = get_oidc_config()
        token_endpoint = config.get("token_endpoint")
        userinfo_endpoint = config.get("userinfo_endpoint")
        
        if not token_endpoint:
            return "Error: OIDC token endpoint not configured", 500
            
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": get_oidc_redirect_uri(),
            "client_id": get_oidc_client_id(),
            "client_secret": get_oidc_client_secret()
        }
        token_res = requests.post(token_endpoint, data=payload, timeout=15)
        token_res.raise_for_status()
        token_data = token_res.json()
        
        access_token = token_data.get("access_token")
        if not access_token:
            return "Error: OIDC token response did not contain access_token", 500
            
        if not userinfo_endpoint:
            return "Error: OIDC userinfo endpoint not configured", 500
            
        userinfo_res = requests.get(userinfo_endpoint, headers={
            "Authorization": f"Bearer {access_token}"
        }, timeout=15)
        userinfo_res.raise_for_status()
        userinfo_data = userinfo_res.json()
        
        email = userinfo_data.get("email") or userinfo_data.get("sub") or userinfo_data.get("preferred_username")
        if not email:
            return "Error: User identification claim not found in userinfo", 500
            
        email = email.lower().strip()
        
        # Check if user is an admin by email OR by OIDC group membership
        user_groups = userinfo_data.get("groups", [])
        if not isinstance(user_groups, list):
            user_groups = []
        is_admin = (email in get_oidc_admin_users()) or (get_oidc_admin_group() in user_groups)
        
        user_row = None
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, is_admin FROM users WHERE email = ?", (email,))
            user_row = cursor.fetchone()
            
            if is_admin:
                if not user_row:
                    cursor.execute(
                        "INSERT INTO users (email, is_admin) VALUES (?, 1)",
                        (email,)
                    )
                else:
                    cursor.execute(
                        "UPDATE users SET is_admin = 1 WHERE email = ?",
                        (email,)
                    )
                conn.commit()
            else:
                # If they are not an administrator, check if they exist in the database (delegated user)
                if not user_row:
                    conn.close()
                    return render_template('login.html', error="You do not have access to this tool. Please contact an administrator.")
                    
            conn.close()
        except Exception as db_err:
            app.logger.error(f"Failed to query/insert OIDC user in database: {db_err}")
            
        # Load user's delegated domains from mapping store
        mapping = load_domain_mapping()
        delegated_domains = mapping.get(email, [])
        
        session["user"] = {
            "email": email,
            "is_admin": is_admin or (user_row and bool(user_row[1])),
            "delegated_domains": delegated_domains
        }
        
        write_audit_log("auth.login", email, email, {"method": "oidc"})
        return redirect(url_for('home'))
    except Exception as e:
        app.logger.error(f"OIDC flow callback failure: {e}")
        return f"Authentication failed: {e}", 500

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login_page'))

@app.route('/api/me')
def get_me():
    user = get_current_user()
    if user:
        email = user.get("email")
        if isinstance(email, str):
            mapping = load_domain_mapping()
            delegated_domains = mapping.get(email, [])
            
            # Fetch is_admin from SQLite to be accurate
            is_admin = False
            try:
                conn = sqlite3.connect(DATABASE_FILE)
                cursor = conn.cursor()
                cursor.execute("SELECT is_admin FROM users WHERE email = ?", (email.lower(),))
                row = cursor.fetchone()
                if row:
                    is_admin = bool(row[0])
                conn.close()
            except Exception:
                pass
                
            if email in get_oidc_admin_users() or email == get_admin_user() or email == "admin@local" or "*" in delegated_domains:
                is_admin = True
                
            user = {**user, "delegated_domains": delegated_domains, "is_admin": is_admin}
            session["user"] = user
            
    return jsonify({
        "success": True,
        "oidc_enabled": is_oidc_enabled(),
        "user": {
            "email": user.get("email"),
            "is_admin": user.get("is_admin", False),
            "delegated_domains": user.get("delegated_domains", [])
        } if user else None
    })

# --- DELEGATIONS ACCESS CONTROL API (ADMIN ONLY) ---

@app.route('/api/admin/delegations', methods=['GET'])
@require_admin
def list_delegations():
    mapping = load_domain_mapping()
    delegations_list = []
    for email, domains in mapping.items():
        delegations_list.append({
            "email": email,
            "domains": domains
        })
    return jsonify({
        "success": True,
        "data": delegations_list
    })

@app.route('/api/admin/delegations', methods=['POST'])
@require_admin
def update_delegation():
    data = request.json or {}
    email = data.get("email")
    domains = data.get("domains")
    password = data.get("password")
    
    if not email:
        return jsonify({"success": False, "error": {"message": "Email is required"}}), 400
    if not isinstance(domains, list):
        return jsonify({"success": False, "error": {"message": "Domains list is required"}}), 400
        
    email = email.strip().lower()
    normalized_domains = [d.strip().lower() for d in domains if d.strip()]
    is_admin = "*" in normalized_domains
    
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        
        from werkzeug.security import generate_password_hash
        hashed_password = generate_password_hash(password) if password else None
        
        if not row:
            # Create user
            cursor.execute(
                "INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, ?)",
                (email, hashed_password, 1 if is_admin else 0)
            )
            user_id = cursor.lastrowid
        else:
            user_id = row[0]
            # Update user
            if password:
                cursor.execute(
                    "UPDATE users SET password_hash = ?, is_admin = ? WHERE id = ?",
                    (hashed_password, 1 if is_admin else 0, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE users SET is_admin = ? WHERE id = ?",
                    (1 if is_admin else 0, user_id)
                )
                
        # Update delegations
        cursor.execute("DELETE FROM delegations WHERE user_id = ?", (user_id,))
        for d in normalized_domains:
            if d == "*":
                continue
            cursor.execute(
                "INSERT INTO delegations (user_id, domain) VALUES (?, ?)",
                (user_id, d)
            )
            
        conn.commit()
        conn.close()
        audit("delegation.update", target=email, domains=normalized_domains, is_admin=is_admin)
        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Error updating user delegations in SQLite: {e}")
        return jsonify({"success": False, "error": {"message": f"Failed to save configuration: {e}"}}), 500

@app.route('/api/admin/delegations', methods=['DELETE'])
@app.route('/api/admin/delegations/<path:email>', methods=['DELETE'])
@require_admin
def delete_delegation(email=None):
    if not email:
        email = request.args.get("email")
    if not email and request.is_json:
        body = request.get_json(silent=True) or {}
        email = body.get("email")
        
    if not email:
        return jsonify({"success": False, "error": {"message": "Email parameter is required"}}), 400
        
    email = email.strip().lower()
    
    current_user = get_current_user()
    if current_user and current_user.get("email", "").lower() == email:
        return jsonify({"success": False, "error": {"message": "Conflict: You cannot revoke/delete your own account."}}), 409
        
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        # Delete user delegations & user record
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if row:
            user_id = row[0]
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            cursor.execute("DELETE FROM delegations WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            audit("delegation.revoke", target=email)
            return jsonify({"success": True})
        return jsonify({"success": False, "error": {"message": "User not found"}}), 404
    except Exception as e:
        app.logger.error(f"Error deleting user delegations from SQLite: {e}")
        return jsonify({"success": False, "error": {"message": f"Failed to delete configuration: {e}"}}), 500

# --- SYSTEM SETTINGS API (ADMIN ONLY) ---

@app.route('/api/admin/settings', methods=['GET'])
@require_admin
def get_settings():
    keys = [
        "OIDC_ENABLED", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_DISCOVERY_URL",
        "OIDC_REDIRECT_URI", "OIDC_SCOPES", "OIDC_ADMIN_USERS", "OIDC_ADMIN_GROUP",
        "MX_SERVER", "MX_USER", "MX_API_KEY", "CF_API_TOKEN", "CF_ACCOUNT_ID",
        "ADMIN_USER", "ADMIN_PASSWORD"
    ]
    settings_dict = {}
    for key in keys:
        settings_dict[key] = get_config_value(key, "")
    return jsonify({
        "success": True,
        "data": settings_dict
    })

@app.route('/api/admin/settings', methods=['POST'])
@require_admin
def update_settings():
    data = request.json or {}
    allowed_keys = [
        "OIDC_ENABLED", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_DISCOVERY_URL",
        "OIDC_REDIRECT_URI", "OIDC_SCOPES", "OIDC_ADMIN_USERS", "OIDC_ADMIN_GROUP",
        "MX_SERVER", "MX_USER", "MX_API_KEY", "CF_API_TOKEN", "CF_ACCOUNT_ID",
        "ADMIN_USER", "ADMIN_PASSWORD"
    ]
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        for key in allowed_keys:
            if key in data:
                val = str(data[key]).strip()
                cursor.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, val)
                )
        conn.commit()
        conn.close()
        
        # Clear the cached OIDC config in case OIDC settings changed
        global _oidc_config, _oidc_config_fetched_at
        with _oidc_config_lock:
            _oidc_config = None
            _oidc_config_fetched_at = 0.0
            
        audit("settings.update", target="system", keys=[key for key in allowed_keys if key in data])
        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Error saving system settings: {e}")
        return jsonify({"success": False, "error": {"message": f"Failed to save settings: {e}"}}), 500

@app.route('/')
def home():
    return render_template('index.html')

# --- CLOUDFLARE INTEGRATION API ---

@app.route('/api/cloudflare/status', methods=['GET'])
@require_admin
def get_cf_status():
    return jsonify({
        "success": True,
        "configured": bool(get_config_value("CF_API_TOKEN") and get_config_value("CF_ACCOUNT_ID"))
    })

@app.route('/api/cloudflare/setup', methods=['POST'])
@require_admin
def cloudflare_setup():
    data = request.json or {}
    domain = data.get("domain")
    if not domain or not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400

    if not cf_is_configured():
        return jsonify({"success": False, "error": {"message": "Cloudflare credentials not configured"}}), 400

    steps = []
    domain = domain.lower().strip()

    try:
        zone_id = ensure_cf_zone(domain, steps)
        verification_record = get_mxroute_verification_record()
        if not verification_record:
            return jsonify({"success": False, "error": {"message": "Failed to get verification key from MXroute"}, "steps": steps}), 500

        steps.append("Fetching existing DNS records from Cloudflare...")
        existing_mx, existing_txt = fetch_cf_dns_sets(zone_id)

        steps.append("Injecting DNS verification TXT record into Cloudflare...")
        deploy_dns_record_to_cf(
            domain, zone_id, "verification", None, verification_record,
            existing_mx, existing_txt, steps,
        )

        steps.append("Registering domain with MXroute platform...")
        register_domain_on_mxroute(domain, steps)

        steps.append("Retrieving MX/SPF/DKIM profiles from MXroute...")
        mx_dns_data = get_mxroute_dns_data(domain)
        if not mx_dns_data:
            return jsonify({"success": False, "error": {"message": "Failed to fetch MXroute DNS configurations"}, "steps": steps}), 500

        steps.append("Deploying mail service records to Cloudflare nameservers...")
        for record_type in MAIL_DNS_RECORD_TYPES:
            deploy_dns_record_to_cf(
                domain, zone_id, record_type, mx_dns_data, verification_record,
                existing_mx, existing_txt, steps,
            )

        steps.append("Domain setup complete! All MXroute and Cloudflare settings active.")
        audit("cloudflare.setup", target=domain, steps=len(steps))
        return jsonify({"success": True, "steps": steps})

    except Exception as e:
        return jsonify({"success": False, "error": {"message": str(e)}, "steps": steps}), 500


@app.route('/api/domains/<domain>/dns/setup-health', methods=['GET'])
@require_admin
def get_dns_setup_health(domain):
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
    health = build_setup_health(domain)
    if not health:
        return jsonify({"success": False, "error": {"message": "Failed to fetch DNS expectations from MXroute"}}), 502
    return jsonify({"success": True, "data": health})


@app.route('/api/domains/<domain>/dns/fix', methods=['POST'])
@require_admin
def fix_domain_dns(domain):
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
    if not cf_is_configured():
        return jsonify({"success": False, "error": {"message": "Cloudflare credentials not configured"}}), 400

    data = request.json or {}
    record_types = data.get("records")

    try:
        result = deploy_missing_dns_to_cf(domain, record_types)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": {"message": str(e)}}), 400

# --- DOMAINS API ---

@app.route('/api/domains', methods=['GET'])
@app.route('/get-domains', methods=['GET']) # backward compat
def get_domains():
    user = get_current_user()
    res, status = mx_request_raw("GET", "/domains")
    if status == 200 and user and not is_user_admin(user):
        email_val = user.get("email")
        email = email_val.lower() if isinstance(email_val, str) else ""
        mapping = load_domain_mapping()
        allowed = [d.lower() for d in mapping.get(email, [])]
        filtered_data = [d for d in res.get("data", []) if d.lower() in allowed]
        res["data"] = filtered_data
    return jsonify(res), status

@app.route('/api/domains', methods=['POST'])
@require_admin
def create_domain():
    data = request.json or {}
    domain = data.get("domain")
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
    return audited_mx("POST", "/domains", request.json, "domain.create", target=domain)

@app.route('/api/domains/<domain>', methods=['GET'])
@require_domain_access
def get_domain_details(domain):
    return mx_request("GET", f"/domains/{domain}")

@app.route('/api/domains/<domain>', methods=['DELETE'])
@require_admin
def delete_domain(domain):
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
    return audited_mx("DELETE", f"/domains/{domain}", None, "domain.delete", target=domain)

@app.route('/api/domains/<domain>/mail-status', methods=['PATCH'])
@require_domain_access
def set_mail_status(domain):
    return audited_mx("PATCH", f"/domains/{domain}/mail-status", request.json, "domain.mail_status", target=domain)

@app.route('/api/verification-key', methods=['GET'])
@require_admin
def get_verification_key():
    return mx_request("GET", "/verification-key")

# --- DOMAIN POINTERS ---

@app.route('/api/domains/<domain>/pointers', methods=['GET'])
@require_domain_access
def list_pointers(domain):
    return mx_request("GET", f"/domains/{domain}/pointers")

@app.route('/api/domains/<domain>/pointers', methods=['POST'])
@require_domain_access
def create_pointer(domain):
    return audited_mx("POST", f"/domains/{domain}/pointers", request.json, "pointer.create", target=domain)

@app.route('/api/domains/<domain>/pointers/<pointer>', methods=['DELETE'])
@require_domain_access
def delete_pointer(domain, pointer):
    return audited_mx("DELETE", f"/domains/{domain}/pointers/{pointer}", None, "pointer.delete", target=f"{pointer}@{domain}")

# --- EMAIL ACCOUNTS ---

@app.route('/api/domains/<domain>/email-accounts', methods=['GET'])
@app.route('/list-emails/<domain>', methods=['GET']) # backward compat
@require_domain_access
def list_emails(domain):
    return mx_request("GET", f"/domains/{domain}/email-accounts")

@app.route('/api/domains/<domain>/email-accounts', methods=['POST'])
@require_domain_access
def create_email_api(domain):
    data = request.json or {}
    username = data.get("username")
    if not validate_username(username):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400
    return audited_mx("POST", f"/domains/{domain}/email-accounts", request.json, "mailbox.create", target=f"{username}@{domain}")

@app.route('/create-email', methods=['POST']) # backward compat (expects Form)
def create_email_compat():
    domain = request.form.get('domain')
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
    
    email_username = request.form.get('user')
    if not validate_username(email_username):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400

    denied = require_compat_domain_access(domain)
    if denied:
        return denied

    password = request.form.get('password')
    payload = {
        "username": email_username,
        "password": password,
        "quota": 0
    }
    return audited_mx("POST", f"/domains/{domain}/email-accounts", payload, "mailbox.create", target=f"{email_username}@{domain}")

@app.route('/api/domains/<domain>/email-accounts/<user>', methods=['GET'])
@require_domain_access
def get_email_account(domain, user):
    return mx_request("GET", f"/domains/{domain}/email-accounts/{user}")

@app.route('/api/domains/<domain>/email-accounts/<user>', methods=['PATCH'])
@require_domain_access
def update_email_account(domain, user):
    if not validate_username(user):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400
    payload = request.json or {}
    action = "mailbox.password_update" if "password" in payload else "mailbox.update"
    return audited_mx("PATCH", f"/domains/{domain}/email-accounts/{user}", payload, action, target=f"{user}@{domain}")

@app.route('/update-password', methods=['POST']) # backward compat (expects Form)
def update_password_compat():
    domain = request.form.get('domain')
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
        
    email_username = request.form.get('user')
    if not validate_username(email_username):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400

    denied = require_compat_domain_access(domain)
    if denied:
        return denied

    password = request.form.get('password')
    payload = {"password": password}
    return audited_mx("PATCH", f"/domains/{domain}/email-accounts/{email_username}", payload, "mailbox.password_update", target=f"{email_username}@{domain}")

@app.route('/api/domains/<domain>/email-accounts/<user>', methods=['DELETE'])
@require_domain_access
def delete_email_api(domain, user):
    if not validate_username(user):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400
    return audited_mx("DELETE", f"/domains/{domain}/email-accounts/{user}", None, "mailbox.delete", target=f"{user}@{domain}")

@app.route('/delete-email', methods=['POST']) # backward compat (expects Form)
def delete_email_compat():
    domain = request.form.get('domain')
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
        
    email_username = request.form.get('user')
    if not validate_username(email_username):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400

    denied = require_compat_domain_access(domain)
    if denied:
        return denied

    return audited_mx("DELETE", f"/domains/{domain}/email-accounts/{email_username}", None, "mailbox.delete", target=f"{email_username}@{domain}")

# --- EMAIL FORWARDERS ---

@app.route('/api/domains/<domain>/forwarders', methods=['GET'])
@require_domain_access
def list_forwarders(domain):
    return mx_request("GET", f"/domains/{domain}/forwarders")

@app.route('/api/domains/<domain>/forwarders', methods=['POST'])
@require_domain_access
def create_forwarder(domain):
    data = request.json or {}
    alias = data.get("alias", "")
    return audited_mx("POST", f"/domains/{domain}/forwarders", request.json, "forwarder.create", target=f"{alias}@{domain}")

@app.route('/api/domains/<domain>/forwarders/<alias>', methods=['DELETE'])
@require_domain_access
def delete_forwarder(domain, alias):
    return audited_mx("DELETE", f"/domains/{domain}/forwarders/{alias}", None, "forwarder.delete", target=f"{alias}@{domain}")

# --- SPAM SETTINGS ---

@app.route('/api/domains/<domain>/spam/settings', methods=['GET'])
@require_domain_access
def get_spam_settings(domain):
    return mx_request("GET", f"/domains/{domain}/spam/settings")

@app.route('/api/domains/<domain>/spam/settings', methods=['PATCH'])
@require_domain_access
def update_spam_settings(domain):
    return audited_mx("PATCH", f"/domains/{domain}/spam/settings", request.json, "spam.settings_update", target=domain)

@app.route('/api/domains/<domain>/spam/whitelist', methods=['GET'])
@require_domain_access
def get_spam_whitelist(domain):
    return mx_request("GET", f"/domains/{domain}/spam/whitelist")

@app.route('/api/domains/<domain>/spam/whitelist', methods=['POST'])
@require_domain_access
def create_spam_whitelist(domain):
    # Expects JSON {"entry": "..."}
    return mx_request("POST", f"/domains/{domain}/spam/whitelist", request.json)

@app.route('/api/domains/<domain>/spam/whitelist/<path:entry>', methods=['DELETE'])
@require_domain_access
def delete_spam_whitelist(domain, entry):
    return mx_request("DELETE", f"/domains/{domain}/spam/whitelist/{entry}")

@app.route('/api/domains/<domain>/spam/blacklist', methods=['GET'])
@require_domain_access
def get_spam_blacklist(domain):
    return mx_request("GET", f"/domains/{domain}/spam/blacklist")

@app.route('/api/domains/<domain>/spam/blacklist', methods=['POST'])
@require_domain_access
def create_spam_blacklist(domain):
    # Expects JSON {"entry": "..."}
    return mx_request("POST", f"/domains/{domain}/spam/blacklist", request.json)

@app.route('/api/domains/<domain>/spam/blacklist/<path:entry>', methods=['DELETE'])
@require_domain_access
def delete_spam_blacklist(domain, entry):
    return mx_request("DELETE", f"/domains/{domain}/spam/blacklist/{entry}")

# --- DNS INFO ---

@app.route('/api/domains/<domain>/dns', methods=['GET'])
@require_domain_access
def get_dns_info(domain):
    res, status = mx_request_raw("GET", f"/domains/{domain}/dns")
    if status == 200 and isinstance(res, dict) and res.get("success"):
        data = res.get("data") or {}
        data["dmarc"] = {
            "name": "_dmarc",
            "value": get_dmarc_record(),
        }
        res["data"] = data
    return jsonify(res), status

@app.route('/api/domains/<domain>/dns/health', methods=['GET'])
@require_domain_access
def get_dns_health(domain):
    mx_dns_res, mx_dns_status = mx_request_raw("GET", f"/domains/{domain}/dns")
    if mx_dns_status != 200:
        return jsonify({"success": False, "error": {"message": "Failed to fetch DNS expectations from MXroute"}}), 502

    verification_record = None
    verify_res, verify_status = mx_request_raw("GET", "/verification-key")
    if verify_status == 200:
        verification_record = verify_res.get("data", {}).get("record")

    health = check_dns_health(
        domain,
        mx_dns_res.get("data", {}),
        verification_record=verification_record,
        dmarc_expected=get_dmarc_record(),
    )

    _, mx_status = mx_request_raw("GET", "/domains")
    health["mxroute_reachable"] = mx_status == 200

    return jsonify({"success": True, "data": health})

# --- CATCH-ALL ---

@app.route('/api/domains/<domain>/catch-all', methods=['GET'])
@require_domain_access
def get_catch_all(domain):
    return mx_request("GET", f"/domains/{domain}/catch-all")

@app.route('/api/domains/<domain>/catch-all', methods=['PATCH'])
@require_domain_access
def update_catch_all(domain):
    return audited_mx("PATCH", f"/domains/{domain}/catch-all", request.json, "catchall.update", target=domain)

# --- QUOTA ---

@app.route('/api/quota', methods=['GET'])
@require_admin
def get_quota():
    return mx_request("GET", "/quota")

@app.route('/api/quota/email', methods=['GET'])
@require_admin
def get_quota_email():
    return mx_request("GET", "/quota/email")

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
