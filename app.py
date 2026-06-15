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

load_dotenv()

app = Flask(__name__)

# Flask Session security key and session cookies hardening
_secret_key = os.getenv("SECRET_KEY")
if not _secret_key:
    app.logger.warning("SECRET_KEY not set — sessions will not persist across restarts or workers!")
    _secret_key = os.urandom(24).hex()
app.secret_key = _secret_key

# OpenID Connect Configuration
OIDC_ENABLED = os.getenv("OIDC_ENABLED", "true").lower() == "true" # Secure by default

app.config.update(
    SESSION_COOKIE_SECURE=OIDC_ENABLED, # Enforce secure session cookies when OIDC is active
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
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID")
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET")
OIDC_DISCOVERY_URL = os.getenv("OIDC_DISCOVERY_URL")
OIDC_REDIRECT_URI = os.getenv("OIDC_REDIRECT_URI")

# Administrators List
admin_users_raw = os.getenv("OIDC_ADMIN_USERS", "")
OIDC_ADMIN_USERS = set(email.strip().lower() for email in admin_users_raw.split(",") if email.strip())

# Local Admin Credentials
ADMIN_USER = os.getenv("ADMIN_USER", "admin").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# Thread-safe persistent storage helper functions
MAPPING_FILE = os.path.join(os.path.dirname(__file__), "domain_mapping.json")
mapping_lock = threading.Lock()

def load_domain_mapping():
    try:
        if os.path.exists(MAPPING_FILE):
            with mapping_lock:
                with open(MAPPING_FILE, 'r') as f:
                    mapping = json.load(f)
                    return {k.lower(): [d.lower() for d in v] for k, v in mapping.items()}
    except Exception as e:
        app.logger.error(f"Error loading domain mapping: {e}")
    return {}

def save_domain_mapping(mapping):
    try:
        with mapping_lock:
            with open(MAPPING_FILE, 'w') as f:
                json.dump(mapping, f, indent=2)
        return True
    except Exception as e:
        app.logger.error(f"Error saving domain mapping: {e}")
        return False

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
    if not OIDC_DISCOVERY_URL:
        raise ValueError("OIDC_DISCOVERY_URL is not configured")
    with _oidc_config_lock:
        # Double-check inside the lock in case another thread already refreshed
        now = time.monotonic()
        if _oidc_config is not None and (now - _oidc_config_fetched_at) < _OIDC_CONFIG_TTL:
            return _oidc_config
        try:
            res = requests.get(OIDC_DISCOVERY_URL, timeout=10)
            res.raise_for_status()
            _oidc_config = res.json()
            _oidc_config_fetched_at = time.monotonic()
            return _oidc_config
        except Exception as e:
            app.logger.error(f"Failed to fetch OIDC configuration: {e}")
            raise

# Active user and permission contexts
def get_current_user():
    if not OIDC_ENABLED:
        return {
            "email": "admin@local",
            "is_admin": True,
            "delegated_domains": []
        }
    return session.get("user")

def is_user_admin(user):
    if not user:
        return False
    email_val = user.get("email")
    email = email_val.lower() if isinstance(email_val, str) else ""
    if email in OIDC_ADMIN_USERS or email == ADMIN_USER or email == "admin@local":
        return True
    mapping = load_domain_mapping()
    if "*" in mapping.get(email, []):
        return True
    # Only trust session is_admin if OIDC is disabled (local development mode)
    if not OIDC_ENABLED:
        return user.get("is_admin", False)
    return False

def has_domain_access(user, domain):
    if not user:
        return False
    if is_user_admin(user):
        return True
    email_val = user.get("email")
    email = email_val.lower() if isinstance(email_val, str) else ""
    mapping = load_domain_mapping()
    return domain.lower() in [d.lower() for d in mapping.get(email, [])]

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

# Route interceptor to enforce login when OIDC is active
@app.before_request
def check_authentication():
    if not OIDC_ENABLED:
        return
    
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
def inject_csrf_token():
    return dict(csrf_token=session.get("csrf_token"))

@app.after_request
def set_csrf_cookie(response):
    if "csrf_token" in session:
        response.set_cookie("csrf_token", session["csrf_token"], samesite="Lax", secure=OIDC_ENABLED)
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


MX_SERVER = os.getenv("MX_SERVER")
MX_USER = os.getenv("MX_USER")
MX_API_KEY = os.getenv("MX_API_KEY")


HEADERS = {
    "X-Server": MX_SERVER,
    "X-Username": MX_USER,
    "X-API-Key": MX_API_KEY,
    "Content-Type": "application/json"
}
BASE_URL = "https://api.mxroute.com"

# Cloudflare Configuration
CF_API_TOKEN = os.getenv("CF_API_TOKEN")
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")

def mx_request_raw(method, path, payload=None):
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            response = requests.get(url, headers=HEADERS, timeout=30)
        elif method == "POST":
            response = requests.post(url, json=payload, headers=HEADERS, timeout=30)
        elif method == "PATCH":
            response = requests.patch(url, json=payload, headers=HEADERS, timeout=30)
        elif method == "DELETE":
            response = requests.delete(url, headers=HEADERS, timeout=30)
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


# Cloudflare Request Helper
def cf_request(method, path, payload=None):
    if not CF_API_TOKEN:
        raise ValueError("Cloudflare API token not configured")

    url = f"https://api.cloudflare.com/client/v4{path}"
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
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

# --- OIDC AUTHENTICATION ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if not OIDC_ENABLED:
        return redirect(url_for('home'))
    
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        
        if ADMIN_PASSWORD and username == ADMIN_USER and secrets.compare_digest(password, ADMIN_PASSWORD):
            session["user"] = {
                "email": username,
                "is_admin": True,
                "delegated_domains": []
            }
            return redirect(url_for('home'))
        else:
            error = "Invalid credentials. Please try again."
            
    return render_template('login.html', error=error)

@app.route('/login/redirect')
def login_redirect():
    if not OIDC_ENABLED:
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
        "client_id": OIDC_CLIENT_ID,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": OIDC_REDIRECT_URI,
        "state": state
    }
    
    auth_url = f"{auth_endpoint}?{urlencode(params)}"
    return redirect(auth_url)

@app.route('/oidc/callback')
def oidc_callback():
    if not OIDC_ENABLED:
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
            "redirect_uri": OIDC_REDIRECT_URI,
            "client_id": OIDC_CLIENT_ID,
            "client_secret": OIDC_CLIENT_SECRET
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
            
        email = email.lower()
        is_admin = email in OIDC_ADMIN_USERS
        
        # Load user's delegated domains from mapping store
        mapping = load_domain_mapping()
        delegated_domains = mapping.get(email, [])
        
        session["user"] = {
            "email": email,
            "is_admin": is_admin,
            "delegated_domains": delegated_domains
        }
        
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
    # Refresh current session dynamic mapping values for accuracy
    if OIDC_ENABLED and user:
        email = user.get("email")
        if isinstance(email, str):
            mapping = load_domain_mapping()
            delegated_domains = mapping.get(email, [])
            is_admin = email in OIDC_ADMIN_USERS or email == ADMIN_USER or "*" in delegated_domains
            # Build a fresh dict rather than mutating in-place to avoid side-effects on existing references
            user = {**user, "delegated_domains": delegated_domains, "is_admin": is_admin}
            session["user"] = user
            
    return jsonify({
        "success": True,
        "oidc_enabled": OIDC_ENABLED,
        "user": {
            "email": user.get("email"),
            "is_admin": user.get("is_admin", False),
            "delegated_domains": user.get("delegated_domains", [])
        } if OIDC_ENABLED and user else None
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
    
    if not email:
        return jsonify({"success": False, "error": {"message": "Email is required"}}), 400
    if not isinstance(domains, list):
        return jsonify({"success": False, "error": {"message": "Domains list is required"}}), 400
        
    email = email.strip().lower()
    normalized_domains = [d.strip().lower() for d in domains if d.strip()]
    
    mapping = load_domain_mapping()
    if not normalized_domains:
        if email in mapping:
            del mapping[email]
    else:
        mapping[email] = normalized_domains
    
    if save_domain_mapping(mapping):
        return jsonify({"success": True})
    return jsonify({"success": False, "error": {"message": "Failed to save delegation configuration"}}), 500

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
    mapping = load_domain_mapping()
    if email in mapping:
        del mapping[email]
        if save_domain_mapping(mapping):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": {"message": "Failed to save delegation configuration"}}), 500
    return jsonify({"success": False, "error": {"message": "User delegation mapping not found"}}), 404

@app.route('/')
def home():
    return render_template('index.html')

# --- CLOUDFLARE INTEGRATION API ---

@app.route('/api/cloudflare/status', methods=['GET'])
@require_admin
def get_cf_status():
    return jsonify({
        "success": True,
        "configured": bool(CF_API_TOKEN and CF_ACCOUNT_ID)
    })

@app.route('/api/cloudflare/setup', methods=['POST'])
@require_admin
def cloudflare_setup():
    data = request.json or {}
    domain = data.get("domain")
    if not domain or not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
        
    if not CF_API_TOKEN or not CF_ACCOUNT_ID:
        return jsonify({"success": False, "error": {"message": "Cloudflare credentials not configured in backend .env"}}), 400

    steps = []
    
    try:
        # Step 1: Find or Create Zone in Cloudflare
        steps.append("Querying Cloudflare for existing Zone...")
        zone_search = cf_request("GET", f"/zones?name={domain}")
        zone_id = None
        if zone_search.get("success") and zone_search.get("result"):
            zone_id = zone_search["result"][0]["id"]
            steps.append(f"Found existing Cloudflare Zone (ID: {zone_id})")
        else:
            steps.append("Creating new Cloudflare Zone...")
            # Create zone
            zone_create = cf_request("POST", "/zones", {
                "name": domain,
                "account": {"id": CF_ACCOUNT_ID},
                "jump_start": True
            })
            if not zone_create.get("success"):
                err_msg = zone_create.get("errors", [{}])[0].get("message", "Unknown Cloudflare error")
                return jsonify({"success": False, "error": {"message": f"Cloudflare Zone creation failed: {err_msg}"}, "steps": steps}), 500
            zone_id = zone_create["result"]["id"]
            steps.append(f"Created new Cloudflare Zone (ID: {zone_id})")
            
        # Step 2: Get verification key from MXroute
        steps.append("Retrieving domain verification details from MXroute...")
        mx_verify_data, mx_verify_status = mx_request_raw("GET", "/verification-key")
        if mx_verify_status != 200:
            return jsonify({"success": False, "error": {"message": "Failed to get verification key from MXroute"}, "steps": steps}), 500
        mx_verify_rec = mx_verify_data.get("data", {}).get("record", {})
        verify_name = mx_verify_rec.get("name")
        verify_value = mx_verify_rec.get("value")
        
        # Query all existing DNS records in Cloudflare for this zone once
        steps.append("Fetching existing DNS records from Cloudflare...")
        cf_dns_search = cf_request("GET", f"/zones/{zone_id}/dns_records?per_page=100")
        existing_records = cf_dns_search.get("result", []) if cf_dns_search.get("success") else []
        
        existing_mx = set()
        existing_txt = set()
        
        for rec in existing_records:
            rtype = rec.get("type")
            rname = rec.get("name", "").lower().rstrip('.')
            rcontent = rec.get("content", "").strip('"')
            if rtype == "MX":
                existing_mx.add((rname, rcontent.lower(), rec.get("priority")))
            elif rtype == "TXT":
                existing_txt.add((rname, rcontent))
        
        # Step 3: Add Verification TXT Record in Cloudflare
        steps.append("Injecting DNS verification TXT record into Cloudflare...")
        verify_name_full = f"{verify_name}.{domain}".lower()
        has_verify = any(rname == verify_name_full and rcontent == verify_value for rname, rcontent in existing_txt)
        if not has_verify:
            verify_dns_add = cf_request("POST", f"/zones/{zone_id}/dns_records", {
                "type": "TXT",
                "name": verify_name,
                "content": verify_value,
                "ttl": 3600
            })
            if not verify_dns_add.get("success"):
                err_msg = verify_dns_add.get("errors", [{}])[0].get("message", "Unknown Cloudflare error")
                return jsonify({"success": False, "error": {"message": f"Failed to add verification TXT: {err_msg}"}, "steps": steps}), 500
            steps.append("Verification TXT record deployed successfully")
            # Add to local cache in case of duplicates
            existing_txt.add((verify_name_full, verify_value))
        else:
            steps.append("Verification TXT record already exists in Cloudflare")
            
        # Step 4: Register Domain with MXroute
        steps.append("Registering domain with MXroute platform...")
        domains_list_res, domains_status = mx_request_raw("GET", "/domains")
        if domains_status == 200 and domain in domains_list_res.get("data", []):
            steps.append("Domain already registered on MXroute")
        else:
            # Register it
            mx_domain_add, mx_add_status = mx_request_raw("POST", "/domains", {"domain": domain})
            if mx_add_status not in [200, 201]:
                err_msg = mx_domain_add.get("error", {}).get("message", "Unknown error")
                return jsonify({"success": False, "error": {"message": f"Failed to register domain with MXroute: {err_msg}"}, "steps": steps}), 500
            steps.append("Domain registered on MXroute successfully")
            
        # Step 5: Fetch DNS configs from MXroute
        steps.append("Retrieving MX/SPF/DKIM profiles from MXroute...")
        mx_dns_res, mx_dns_status = mx_request_raw("GET", f"/domains/{domain}/dns")
        if mx_dns_status != 200:
            return jsonify({"success": False, "error": {"message": "Failed to fetch MXroute DNS configurations"}, "steps": steps}), 500
        mx_dns_data = mx_dns_res["data"]
        
        # Step 6: Create MX, SPF, DKIM records in Cloudflare
        steps.append("Deploying mail service records to Cloudflare nameservers...")
        
        # Add MX records
        if mx_dns_data.get("mx_records"):
            for mx in mx_dns_data["mx_records"]:
                mx_host = mx["hostname"].lower().rstrip('.')
                mx_priority = mx["priority"]
                has_mx = any(
                    rname == domain.lower() and rcontent == mx_host
                    and int(rpriority or 0) == int(mx_priority or 0)
                    for rname, rcontent, rpriority in existing_mx
                )
                if not has_mx:
                    cf_request("POST", f"/zones/{zone_id}/dns_records", {
                        "type": "MX",
                        "name": "@",
                        "content": mx["hostname"],
                        "priority": mx["priority"],
                        "ttl": 3600
                    })
            steps.append("MX records configured")
            
        # Add SPF record
        if mx_dns_data.get("spf"):
            spf_val = mx_dns_data["spf"]["value"]
            has_spf = any(
                rname == domain.lower() and rcontent.startswith("v=spf1")
                for rname, rcontent in existing_txt
            )
            if not has_spf:
                cf_request("POST", f"/zones/{zone_id}/dns_records", {
                    "type": "TXT",
                    "name": "@",
                    "content": spf_val,
                    "ttl": 3600
                })
                steps.append("SPF record configured")
            else:
                steps.append("SPF record exists (skipping)")
                
        # Add DKIM record
        if mx_dns_data.get("dkim"):
            dkim_name = mx_dns_data["dkim"]["name"]
            dkim_val = mx_dns_data["dkim"]["value"]
            dkim_host_part = dkim_name.replace(f".{domain}", "")
            dkim_name_full = f"{dkim_host_part}.{domain}".lower()
            
            has_dkim = any(rname == dkim_name_full for rname, rcontent in existing_txt)
            if not has_dkim:
                cf_request("POST", f"/zones/{zone_id}/dns_records", {
                    "type": "TXT",
                    "name": dkim_host_part,
                    "content": dkim_val,
                    "ttl": 3600
                })
                steps.append("DKIM record configured")
            else:
                steps.append("DKIM record exists (skipping)")
                
        steps.append("Domain setup complete! All MXroute and Cloudflare settings active.")
        return jsonify({"success": True, "steps": steps})
        
    except Exception as e:
        return jsonify({"success": False, "error": {"message": str(e)}, "steps": steps}), 500

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
    return mx_request("POST", "/domains", request.json)

@app.route('/api/domains/<domain>', methods=['GET'])
@require_domain_access
def get_domain_details(domain):
    return mx_request("GET", f"/domains/{domain}")

@app.route('/api/domains/<domain>', methods=['DELETE'])
@require_admin
def delete_domain(domain):
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
    return mx_request("DELETE", f"/domains/{domain}")

@app.route('/api/domains/<domain>/mail-status', methods=['PATCH'])
@require_domain_access
def set_mail_status(domain):
    # Expects JSON {"enabled": true/false}
    return mx_request("PATCH", f"/domains/{domain}/mail-status", request.json)

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
    # Expects JSON {"pointer": "...", "alias": true/false}
    return mx_request("POST", f"/domains/{domain}/pointers", request.json)

@app.route('/api/domains/<domain>/pointers/<pointer>', methods=['DELETE'])
@require_domain_access
def delete_pointer(domain, pointer):
    return mx_request("DELETE", f"/domains/{domain}/pointers/{pointer}")

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
    # Expects JSON {"username": "...", "password": "...", "quota": ..., "limit": ...}
    return mx_request("POST", f"/domains/{domain}/email-accounts", request.json)

@app.route('/create-email', methods=['POST']) # backward compat (expects Form)
def create_email_compat():
    domain = request.form.get('domain')
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
    
    email_username = request.form.get('user')
    if not validate_username(email_username):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400
        
    if OIDC_ENABLED:
        current_user = get_current_user()
        if not current_user or not has_domain_access(current_user, domain):
            return jsonify({"success": False, "error": {"message": f"Forbidden: You do not have access to domain '{domain}'"}}), 403
    password = request.form.get('password')
    payload = {
        "username": email_username,
        "password": password,
        "quota": 0
    }
    return mx_request("POST", f"/domains/{domain}/email-accounts", payload)

@app.route('/api/domains/<domain>/email-accounts/<user>', methods=['GET'])
@require_domain_access
def get_email_account(domain, user):
    return mx_request("GET", f"/domains/{domain}/email-accounts/{user}")

@app.route('/api/domains/<domain>/email-accounts/<user>', methods=['PATCH'])
@require_domain_access
def update_email_account(domain, user):
    if not validate_username(user):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400
    # Expects JSON {"password": "...", "quota": ..., "limit": ...}
    return mx_request("PATCH", f"/domains/{domain}/email-accounts/{user}", request.json)

@app.route('/update-password', methods=['POST']) # backward compat (expects Form)
def update_password_compat():
    domain = request.form.get('domain')
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
        
    email_username = request.form.get('user')
    if not validate_username(email_username):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400
        
    if OIDC_ENABLED:
        current_user = get_current_user()
        if not current_user or not has_domain_access(current_user, domain):
            return jsonify({"success": False, "error": {"message": f"Forbidden: You do not have access to domain '{domain}'"}}), 403
    password = request.form.get('password')
    payload = {"password": password}
    return mx_request("PATCH", f"/domains/{domain}/email-accounts/{email_username}", payload)

@app.route('/api/domains/<domain>/email-accounts/<user>', methods=['DELETE'])
@require_domain_access
def delete_email_api(domain, user):
    if not validate_username(user):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400
    return mx_request("DELETE", f"/domains/{domain}/email-accounts/{user}")

@app.route('/delete-email', methods=['POST']) # backward compat (expects Form)
def delete_email_compat():
    domain = request.form.get('domain')
    if not validate_domain(domain):
        return jsonify({"success": False, "error": {"message": "Invalid domain name format"}}), 400
        
    email_username = request.form.get('user')
    if not validate_username(email_username):
        return jsonify({"success": False, "error": {"message": "Invalid mailbox username format"}}), 400
        
    if OIDC_ENABLED:
        current_user = get_current_user()
        if not current_user or not has_domain_access(current_user, domain):
            return jsonify({"success": False, "error": {"message": f"Forbidden: You do not have access to domain '{domain}'"}}), 403
    return mx_request("DELETE", f"/domains/{domain}/email-accounts/{email_username}")

# --- EMAIL FORWARDERS ---

@app.route('/api/domains/<domain>/forwarders', methods=['GET'])
@require_domain_access
def list_forwarders(domain):
    return mx_request("GET", f"/domains/{domain}/forwarders")

@app.route('/api/domains/<domain>/forwarders', methods=['POST'])
@require_domain_access
def create_forwarder(domain):
    # Expects JSON {"alias": "...", "destinations": [...]}
    return mx_request("POST", f"/domains/{domain}/forwarders", request.json)

@app.route('/api/domains/<domain>/forwarders/<alias>', methods=['DELETE'])
@require_domain_access
def delete_forwarder(domain, alias):
    return mx_request("DELETE", f"/domains/{domain}/forwarders/{alias}")

# --- SPAM SETTINGS ---

@app.route('/api/domains/<domain>/spam/settings', methods=['GET'])
@require_domain_access
def get_spam_settings(domain):
    return mx_request("GET", f"/domains/{domain}/spam/settings")

@app.route('/api/domains/<domain>/spam/settings', methods=['PATCH'])
@require_domain_access
def update_spam_settings(domain):
    # Expects JSON {"high_score": ...}
    return mx_request("PATCH", f"/domains/{domain}/spam/settings", request.json)

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
    return mx_request("GET", f"/domains/{domain}/dns")

# --- CATCH-ALL ---

@app.route('/api/domains/<domain>/catch-all', methods=['GET'])
@require_domain_access
def get_catch_all(domain):
    return mx_request("GET", f"/domains/{domain}/catch-all")

@app.route('/api/domains/<domain>/catch-all', methods=['PATCH'])
@require_domain_access
def update_catch_all(domain):
    # Expects JSON {"type": "...", "address": "..."}
    return mx_request("PATCH", f"/domains/{domain}/catch-all", request.json)

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
