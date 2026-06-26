# Changelog

All notable changes to MXroute Manager are documented here and on [GitHub Releases](https://github.com/t0msh/mxroute-manager/releases).

The format follows [Keep a Changelog](https://keepachangelog.com/). Version numbers match `APP_VERSION` in `app_meta.py`. **Each release entry must match the GitHub release notes for that tag** (write once, publish twice).

## [Unreleased]

### Added

- Contributing guide (`docs/contributing.md`) with coding standards, PR expectations, and MkDocs nav entry.

## [0.18.0] - 2026-06-26

Minor release: generic deploy tooling for local and remote hosts.

### Added

- **`deploy.sh`**: interactive menu for local or SSH remote Docker deploys; save settings in `deploy.conf` for `./deploy.sh -y` later. See [Getting started](docs/getting-started.md).

### Upgrade

```bash
git pull
./deploy.sh   # or docker compose up --build -d
```

## [0.17.8] - 2026-06-26

Patch release: auth boundary hardening and outbound request validation.

### Security

- Reload grants and admin flags from the database on each request.
- SQLite-backed rate limits; SSRF guards for Apprise, OIDC, and SMTP outbound calls.
- POST logout with CSRF; CSP script nonces on templates.
- Fleet refresh and password-reset portal isolation tightened.

### Upgrade

```bash
git pull
pip install -r requirements.txt
# restart the app
```

## [0.17.7] - 2026-06-26

Patch release: relax MX and DMARC DNS health checks. Fixes [#13](https://github.com/t0msh/mxroute-manager/issues/13).

### Fixed

- **MX:** passes when expected MXroute hostnames are present; priority values no longer need to match exactly.
- **DMARC:** passes for valid live records (`p=reject`, `p=quarantine`, etc.) instead of warning when they differ from the default template.
- **Custom DMARC:** policies match on `p`/`sp` tags so extra `rua`/`ruf` addresses in DNS do not fail the check.

## [0.17.6] - 2026-06-26

Patch release: CodeQL model pack cleanup and API token hashing upgrade.

### Security

- API tokens now use **PBKDF2-HMAC-SHA256** (600k iterations) instead of bare HMAC-SHA256. **Regenerate API tokens** after upgrade if you deployed v0.17.5.

### Changed

- CodeQL sanitizer model pack moved to `.github/codeql/extensions/` for auto-discovery.

## [0.17.5] - 2026-06-25

Patch release: CodeQL hardening and domain-scoped MXroute proxy helpers.

### Security

- API tokens hashed with **HMAC-SHA256** keyed on `SECRET_KEY` (replacing bare SHA-256). **Regenerate tokens** after upgrade.
- Domain-scoped MXroute proxy validates domains before upstream calls; sanitized JSON responses.

## [0.17.4] - 2026-06-25

Patch release: CodeQL follow-up and auth route split (no behaviour change).

### Security

- Sanitize all MX API JSON before browser delivery; re-validate audit log paths before `send_file`.

### Changed

- Split `routes/auth.py` into `auth_local`, `auth_oidc`, `auth_profile`, and `auth_session` modules.

## [0.17.3] - 2026-06-25

Patch release: OIDC login hardening and path confinement.

### Security

- Reject OIDC sign-in when `email` is present without `email_verified`.
- Confine logo, audit log, and Traefik config access under validated base paths.

## [0.17.2] - 2026-06-25

Patch release: deploy the missing `mail.<domain>` CNAME during DNS setup.

### Fixed

- **`mail.<domain>` CNAME** now deployed in the setup wizard, `/api/cloudflare/setup`, and bulk DNS repair (was webmail-only before).
- New **Mail server (CNAME)** health check in wizard, dashboard, and fleet overview.

## [0.17.1] - 2026-06-25

Patch release: DNS health fixes, per-domain DMARC, notification branding. Fixes [#10](https://github.com/t0msh/mxroute-manager/issues/10).

### Added

- Per-domain DMARC policies (wizard + domain actions menu).
- Notification avatar branding via `MANAGER_PUBLIC_URL` or `NOTIFICATION_AVATAR_URL`.

### Fixed

- **SPF:** health passes when the live record is a superset of the MXroute SPF.
- **DMARC:** valid non-default `p=` values warn instead of hard-fail when no per-domain override is set.

## [0.17.0] - 2026-06-24

### Added

- API tokens for automation.
- Fleet overview dashboard with DB-backed caching.
- Bulk CSV mailbox import/export.
- Quota alerts and audit log downloads.
- Unicorn Puke and Cotton Candy rainbow themes.
- MkDocs documentation site.

## [0.16.0] - 2026-06-23

### Added

- Branded password-reset portals with one-click deploy (Cloudflare DNS + TLS).
- Multi reverse-proxy backends: NPM, Cloudflare Tunnel, Caddy, Traefik, manual.
- 4-step domain onboarding wizard; Apprise audit notifications.
- Split monoliths (`app.js`, `db.py`, `cloudflare.py`); aislop quality gate; expanded tests.

---

**Earlier releases:** [GitHub Releases](https://github.com/t0msh/mxroute-manager/releases) (v0.2.0 and up).
