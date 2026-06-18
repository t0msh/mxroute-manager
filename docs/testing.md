# Testing

How the test suite works in this repo — what we check, how it's set up, and how to run or add tests. No MXroute, Cloudflare, or NPM credentials needed; everything hits a throwaway SQLite DB and mocked APIs.

## What we're trying to catch

Tests focus on stuff that would be embarrassing or dangerous if it broke:

- Who can access which domain (auth + delegations)
- Mailbox and recovery-email handling
- DNS setup being safe to re-run (no duplicate records)
- Password-reset portals staying isolated

We're **not** chasing 100% line coverage. External APIs are mocked; SQLite is real but thrown away after each run.

## Running tests

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

That single command also runs **JavaScript unit tests** (`static/js/*.test.js` via Node's built-in `node --test`). You need Node 18+ on your machine; CI installs it automatically.

JS only:

```bash
node --test static/js/
```

Coverage report (same as CI):

```bash
pytest --cov=services --cov=models --cov=utils --cov-report=term-missing
```

One file or one test:

```bash
pytest tests/test_emails.py -v
pytest tests/test_emails.py::test_create_email_saves_recovery_on_success -v
```

GitHub Actions runs this on every push and PR — see [`.github/workflows/test.yml`](../.github/workflows/test.yml).

## Three layers (fast → thorough)

### Layer 1 — Pure logic

**Files:** `test_validators.py`, `test_auth_helpers.py`, `static/js/*.test.js`

Plain functions, plain asserts. No DB, no HTTP, no mocks.

Good for validation rules and permission math — when something fails, you know exactly which function misbehaved.

Frontend helpers live in `static/js/` as ES modules (`permissions.js`, `utils.js`, `cache.js`). `browser-entry.js` loads them onto `window.Mxm` before `app.js` runs; `app.js` keeps thin wrappers so onclick handlers still work. Tests use Node's built-in runner — no `npm install`, no Vitest.

### Layer 2 — Services with mocks

**Files:** `test_cloudflare_idempotent.py`, `test_reset_portal_dns.py`, etc.

Real service code runs; `cf_request`, `mx_request_raw`, DNS lookups get patched out.

Good for "read before write" DNS logic and deploy orchestration without hitting the network.

```python
with patch("services.cloudflare.cf_request") as mock_cf:
    result = cf_upsert_txt(...)
mock_cf.assert_not_called()  # already correct — skip create
```

### Layer 3 — HTTP through Flask

**Files:** `test_auth_delegation.py`, `test_emails.py`, `test_forwarders.py`, `test_spam.py`, `test_reset_portal.py`

`test_client()` sends real requests through auth, CSRF, decorators, and route handlers. MXroute/Cloudflare still mocked; SQLite is real.

Good for wiring bugs — wrong decorator, CSRF forgotten, session shape wrong, DB side effect missing after a successful API call.

## Shared plumbing

### `tests/conftest.py`

Runs before anything else:

1. Creates a temp `.db` and sets `DATABASE_FILE` **before** `models.db` imports (it reads that path at import time).
2. Sets dummy Cloudflare/NPM env vars so deploy code doesn't complain.
3. Provides fixtures: `fresh_db`, `client`, `db_connection`.

### `tests/helpers.py`

| Helper | What it does |
| --- | --- |
| `insert_user_with_grants()` | User + delegation rows in SQLite |
| `prime_authenticated_session()` | Log in via session (matches real login shape) |
| `auth_post_headers()` | CSRF + JSON for POST/PATCH/DELETE |
| `mx_json_response()` | Fake MXroute response tuple for mocks |
| `csrf_token_from_response()` | Pull CSRF cookie from a GET |

### Cleaning up between tests

Route tests often use an `autouse` fixture that wipes `users`, `delegations`, etc. before each test. We share one session DB file — without cleanup you get `UNIQUE constraint` explosions and weird cross-test pollution.

## Mocking externals

Patch where the route imports the function:

| Service | Patch target |
| --- | --- |
| MXroute | `routes.emails.*`, `routes.spam.*`, `routes.domains.*` |
| OIDC token/userinfo | `routes.auth.requests.post`, `routes.auth.requests.get` (or patch `get_oidc_config` for discovery) |
| Cloudflare | `services.cloudflare.cf_request`, `routes.cloudflare.*` |
| NPM | `services.reset_portal_deploy.*` |
| Public DNS | `dns.resolver.Resolver`, etc. |

CI should never need real API keys.

### Fake MXroute responses

```python
from tests.helpers import mx_json_response

with patch("routes.emails.audited_mx", return_value=mx_json_response({"success": True}, 201)):
    response = client.post("/api/domains/example.com/email-accounts", ...)
```

`mx_json_response` builds a real Flask `Response` inside an app context — same shape production returns.

## Auth in tests

Protected routes need:

1. A session user (`prime_authenticated_session` after inserting the user in SQLite)
2. CSRF header on anything that mutates state

Delegated users go in via `insert_user_with_grants()` — permissions should match what you'd set in the Access Control UI.

OIDC tests use `enable_oidc_settings()` plus `patch_oidc_http()` to fake the token and userinfo endpoints. `prime_oidc_state()` seeds the CSRF `state` the callback expects in session.

## What's covered

| Area | Tests | Layer |
| --- | --- | --- |
| Validators | `test_validators.py` | 1 |
| Permission helpers | `test_auth_helpers.py` | 1 |
| Login, delegations, admin API | `test_auth_delegation.py` | 3 |
| OIDC redirect + callback | `test_oidc.py` | 3 |
| Mailboxes + recovery email | `test_emails.py` | 3 |
| Forwarders, catch-all, pointers | `test_forwarders.py` | 3 |
| Spam settings, lists | `test_spam.py` | 3 |
| Password reset tokens (DB) | `test_password_reset.py` | 1–2 |
| Public password-reset API | `test_password_reset_api.py` | 3 |
| DNS health comparison | `test_dns_health.py` | 2 |
| Domain admin routes | `test_domains.py` | 3 |
| Settings cache | `test_settings_cache.py` | 2 |
| Cloudflare idempotency | `test_cloudflare_idempotent.py` | 2 |
| Cloudflare DNS fix (`deploy_missing_dns_to_cf`) | `test_cloudflare_dns_fix.py` | 2 |
| Cloudflare DNS wizard (HTTP) | `test_cloudflare_wizard.py` | 3 |
| Reset portal routing / CSRF | `test_reset_portal.py` | 3 |
| Portal DNS checks | `test_reset_portal_dns.py` | 2 |
| Portal deploy | `test_reset_portal_deploy.py` | 2 |
| Frontend JS (permissions, utils, cache) | `static/js/*.test.js` + `test_javascript.py` | 1 |

## What's not covered yet

Being upfront about gaps:

- Most of `static/app.js` (DOM wiring, API orchestration — only extracted pure helpers are tested)
- Load / concurrency stress

PRs welcome in those areas; same patterns as above.

## Adding a test

1. Pick the layer — don't use Flask if you don't need it.
2. Use `conftest` fixtures + `tests/helpers.py`.
3. Clean up DB state if your test writes rows.
4. Mock externals; use `assert_not_called()` when validation should block before MXroute.
5. `pytest your_file.py -v` before you push.

### Example pattern

```python
def test_create_email_rejects_invalid_username(fresh_db, client, emails_token):
    with patch("routes.emails.audited_mx") as mock_mx:
        response = client.post(
            "/api/domains/example.com/email-accounts",
            headers=auth_post_headers(emails_token),
            json={"username": "bad name", "password": "Abcd123!"},
        )
    assert response.status_code == 400
    mock_mx.assert_not_called()
```

Status code → side effects → mock called or not. That's the usual shape.

## Config files

| File | Role |
| --- | --- |
| `requirements-dev.txt` | pytest + pytest-cov |
| `pytest.ini` | finds `tests/test_*.py` |
| `static/js/*.test.js` | Node `node --test` frontend unit tests |
| `.github/workflows/test.yml` | CI (Python + Node) |

## Keeping this doc honest

If you add tests in a new area, tweak this file in the same PR so it still matches reality. Future-you (and anyone else poking around) will thank you.
