# Local admin password

MXroute Manager supports a local break-glass admin account (`ADMIN_USER` / `ADMIN_PASSWORD`) alongside optional OIDC. This guide covers how that password is stored, common login mistakes, and how to reset it when locked out.

Environment variable reference: [Authentication](configuration.md#authentication) in the configuration guide.

## How the database is seeded

On first startup, `init_db()` reads `ADMIN_PASSWORD` from the environment and stores a **bcrypt hash** in SQLite (`ADMIN_PASSWORD_HASH` in the `settings` table). If no admin user exists yet, it also creates a row in `users` for `ADMIN_USER` with that same hash.

After that initial seed:

- Login checks the **stored hash in the database**, not the live `.env` value.
- Editing `ADMIN_PASSWORD` in `.env` and restarting **does not** change the stored hash.
- The plaintext password in `.env` is optional to keep; it is only used for that first seed (or a forced re-sync below).

This is intentional: the database is the source of truth for credentials, and `.env` is a bootstrap convenience.

## Signing in

| Use | Do not use |
| --- | --- |
| `ADMIN_USER` (default `admin`) | OIDC email addresses (e.g. `you@example.com`) unless that user has their own local password in **Access Control** |

**Docker note:** `docker-compose.yml` sets `DATABASE_FILE=/data/mxroute-manager.db` on a named volume. That file is independent of `mxroute-manager.db` in a dev checkout. Seeding and resets apply to whichever database the running instance actually uses.

**While signed in:** change the password under **Settings → Local Admin Password**. That updates both `ADMIN_PASSWORD_HASH` and the matching `users` row immediately.

## Resetting a forgotten password

### Option 1 — Re-sync from `.env` (recommended)

Set the new password in `.env`, enable the one-shot flag, and restart the app once:

```env
ADMIN_PASSWORD=your_new_secure_password
ADMIN_PASSWORD_FORCE_SYNC=true
```

After a successful restart, sign in with `ADMIN_USER` and the new password, then remove the flag or set `ADMIN_PASSWORD_FORCE_SYNC=false` so the password cannot be reset from `.env` on every future restart.

For Docker:

```bash
# edit .env, then:
docker compose up -d
```

### Option 2 — Python one-liner

From the app directory (or inside the container), with the same `DATABASE_FILE` the running app uses:

```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from models.db import set_admin_password_hash
import os
set_admin_password_hash(os.environ['ADMIN_PASSWORD'])
print('Admin password hash updated.')
"
```

Restart is not required for the hash change itself, but restart if you are unsure the app is pointing at the same database file.

Docker example:

```bash
docker compose exec mxroute-manager python3 -c "
from dotenv import load_dotenv; load_dotenv()
from models.db import set_admin_password_hash
import os
set_admin_password_hash(os.environ['ADMIN_PASSWORD'])
print('Admin password hash updated.')
"
```

### Option 3 — Already signed in

If you still have an admin session (e.g. via OIDC), change the password in **Settings** without touching `.env`.

### Option 4 — Nuclear reset (last resort)

Deleting the SQLite database (or the Docker volume) and restarting recreates an empty DB and re-seeds from the current `ADMIN_PASSWORD` in `.env`. You will lose delegations, settings saved in the UI, and other local data. Only use this on a fresh install or when you have backups.
