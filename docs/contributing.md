# Contributing

Thanks for poking at this. MXroute Manager is a side project that grew up fast: Flask backend, classic JS frontend, SQLite, and a lot of real-world DNS pain baked in. Pull requests are welcome. This file is the short version of how we write code here so you do not have to reverse-engineer it from scattered rules.

## Before you open a PR

1. Fork or branch from `dev` (day-to-day work lands there; `main` is releases).
2. Install dev deps and run the test suite:

   ```bash
   pip install -r requirements-dev.txt
   pytest
   ```

   That runs Python tests and `static/js/*.test.js` via Node. You need Node 18+ locally; CI uses Node 22. Details: [testing.md](testing.md).

3. If you touch user-facing behaviour, update the matching doc under `docs/` in the same PR. Docs ship with the code.
4. Open the PR against `dev`. CI runs pytest and an [aislop](https://github.com/scanaislop/aislop) quality check on changed files.

No MXroute or Cloudflare keys are required to test. Externals are mocked; SQLite is real but throwaway.

## How we think about code

**Lazy does not mean careless.** The best code is often the code you never wrote. Before adding anything, ask:

1. Does this need to exist at all?
2. Does the stdlib (or something already in the repo) do it?
3. Can it be one line? Make it one line.
4. Only then: write the minimum that works.

Practical corollaries:

- No abstractions nobody asked for.
- No new dependency if stdlib or an existing package covers it.
- Deletion over addition. Boring over clever. Fewest files possible.
- **Do** be thorough at trust boundaries: input validation, auth, CSRF, rate limits, audit logging, anything that prevents data loss.

When you take an intentional shortcut (global cache, single-process lock, naive O(n) scan), leave a `ponytail:` comment that names the ceiling and the upgrade path. Examples are scattered through `services/`, `models/`, and `static/js/app/`.

## Project layout

| Area | Where | Notes |
| --- | --- | --- |
| Flask app entry | `app.py` | Middleware, blueprints, portal routing |
| HTTP routes | `routes/` | Thin handlers; call into services |
| Business logic | `services/` | MXroute, Cloudflare, DNS, mail, notifications |
| Data layer | `models/` | SQLite schema and queries |
| Shared helpers | `utils/` | Auth, validators, audit, Apprise builders |
| Frontend modules | `static/js/` | ES modules (`permissions.js`, `utils.js`, `cache.js`) on `window.Mxm` |
| Frontend app scripts | `static/js/app/` | Classic scripts, shared global scope, `onclick` from templates |
| Templates | `templates/` | Jinja; script load order matters |
| Tests | `tests/`, `static/js/*.test.js` | See [testing.md](testing.md) |
| Version | `app_meta.py` | `APP_VERSION` is the single source of truth |

Keep route handlers thin. Put orchestration in `services/`, persistence in `models/`.

## Rules that bite if you ignore them

### Idempotent setup

Domain registration, Cloudflare DNS, and mailbox creation must be **safe to re-run**. Wizards and repair flows get clicked twice. Always:

- **Read before write** (list zones, records, domains, or mailboxes before `POST`).
- **Skip when correct** (already matches desired state).
- **Upsert when wrong** (update in place; do not blindly create duplicates).
- **Report outcome** (`skipped`, `added`, `updated`) so the UI can show progress.

Duplicate-create API errors are a last resort, not the primary guard.

### Third-party API concurrency

Never fire unbounded parallel requests at MXroute, Cloudflare, or similar APIs.

- **Python:** `ThreadPoolExecutor` with a modest `max_workers` (typically 3 to 10), or fixed-size chunks.
- **JavaScript:** use a small concurrency limiter or sequential batches. No `Promise.all(domains.map(...))` against live APIs.

See `.cursor/rules/api-concurrency.mdc` for canonical patterns.

### Size limits

[aislop](https://github.com/scanaislop/aislop) enforces rough ceilings (see `.aislop/config.yml`):

| Limit | Value |
| --- | --- |
| Max function length | ~80 lines |
| Max file length | ~400 lines |
| Max nesting depth | 5 |
| Max parameters | 6 |

Split files when they grow (the frontend already follows this; see [frontend-app-scripts.md](frontend-app-scripts.md)).

## Python

- Match surrounding style: plain functions, explicit imports, no framework magic beyond Flask.
- Patch mocks at the import site the route uses (documented in [testing.md](testing.md)).
- Prefer stdlib `concurrent.futures` over extra async stacks for batch API work.
- Sensitive paths already use CSRF, session checks, Bearer tokens, rate limits, and audit logging. New mutating routes should follow existing patterns in `routes/auth_*.py` and neighbours.

## Frontend

No bundler. Two layers:

1. **ES modules** in `static/js/` for pure logic (permissions, caching, utils). Loaded via `browser-entry.js` onto `window.Mxm`.
2. **Classic scripts** in `static/js/app/` for DOM wiring. They share one global scope with inline `onclick` handlers.

If you add or reorder app scripts, update **both** `templates/index.html` and [frontend-app-scripts.md](frontend-app-scripts.md). `init.js` loads late on purpose.

Extract testable logic into `static/js/` modules when you can. DOM orchestration in `static/js/app/` is still mostly manual-test territory.

## Tests

We are not chasing 100% line coverage. We **do** want tests for things that would be embarrassing or dangerous if they broke: auth, delegations, idempotent DNS, password-reset isolation, CSRF wiring.

Pick the lightest layer that proves your change:

| Layer | When |
| --- | --- |
| 1 - Pure logic | Validators, permission math, JS helpers. No DB, no HTTP. |
| 2 - Services + mocks | Cloudflare/MXroute orchestration with patched `cf_request` / `mx_request_raw`. |
| 3 - Flask HTTP | Full request through auth, decorators, and SQLite side effects. |

Use `tests/conftest.py` fixtures and `tests/helpers.py`. Clean up DB rows when your test writes data. Use `assert_not_called()` on mocks when validation should block before an external API runs.

Add a test in the same PR when you fix non-trivial logic. Trivial one-liners do not need a ceremony.

## Quality gate (aislop)

PRs run `aislop ci --changes` against the base branch. It catches dead imports, narrative comments, oversized functions, sloppy error handling, and other patterns that slip in when AI helps write the first draft.

- Treat `error` findings and fixable `warning` findings as blocking.
- Do not disable rules to green the build. Fix the underlying issue.
- Config lives in `.aislop/config.yml`. Do not change thresholds without a good reason.

Badge on the README links to the public scoreboard if you are curious how we are doing overall.

## Docs and MkDocs

User guides live in `docs/`. The site is built with MkDocs Material (`mkdocs serve` for local preview). If you add a feature, add or extend the guide that a user would actually open. Keep [README.md](README.md) honest if you add a new top-level doc.

## Version bumps and releases

**Routine PRs to `dev` do not need a version bump.**

When work merges to `main` for a release, bump `APP_VERSION` in `app_meta.py` once for the batch:

| Change | Bump |
| --- | --- |
| New feature, new tab, API surface, UX overhaul | minor |
| Bug fix, small tweak | patch |
| Breaking config or API contract (while `0.x`) | minor |

Tag `main` as `v{APP_VERSION}` after release. Update `CHANGELOG.md` and publish matching GitHub release notes (see `release-changelog.mdc` in `.cursor/rules/`). Maintainers handle this on release; contributors usually skip it unless asked.

## PR checklist

- [ ] `pytest` passes locally
- [ ] New behaviour has tests at the appropriate layer
- [ ] Setup flows are idempotent where they touch MXroute or Cloudflare
- [ ] Batch external calls are concurrency-limited
- [ ] User-facing docs updated if behaviour changed
- [ ] No secrets, `.env` values, or `build_info.py` in the diff

## Questions

Open a [GitHub issue](https://github.com/t0msh/mxroute-manager/issues) or a draft PR if you are unsure about approach. Smaller, focused PRs review faster than kitchen-sink diffs.

## Related guides

| Guide | Topic |
| --- | --- |
| [testing.md](testing.md) | Fixtures, layers, mocking |
| [frontend-app-scripts.md](frontend-app-scripts.md) | Script load order |
| [api.md](api.md) | HTTP API for automation |
| [Main README](https://github.com/t0msh/mxroute-manager/blob/main/README.md) | Quickstart and feature overview |
