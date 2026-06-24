# Frontend app scripts

The main UI logic used to live in a single `static/app.js` file. It is now split across `static/js/app/` as classic (non-module) scripts. They share one global scope with each other and with inline `onclick` handlers in templates.

Pure helpers that do not need the DOM live in ES modules under `static/js/` (`permissions.js`, `utils.js`, `cache.js`, etc.). `browser-entry.js` loads those onto `window.Mxm` before any app script runs.

## Load order

Scripts must load in the order below. `templates/index.html` lists them in this sequence. If you add or reorder files, update both the template and this document.

| File | Role |
| --- | --- |
| `state-api.js` | App state, permissions wrappers, `apiRequest`, JSON parsing |
| `table-controls.js` | Shared search + pagination for domain and mailbox tables |
| `api-cache.js` | `cachedFetch`, `fetchCachedList`, cache invalidation, refresh indicators |
| `ui.js` | Alerts, modals, action menus, mobile nav, shared UI helpers |
| `domains-list.js` | Domain table list, bulk DNS fix, domain action menu markup |
| `domains-rows.js` | Per-row status refresh, mail/DNS cells, paginated domain render |
| `domain-detail.js` | Single-domain detail panel |
| `portal.js` | Reset portal settings, deploy, logo upload |
| `setup-dns.js` | Setup wizard DNS health display |
| `setup-wizard.js` | Multi-step domain setup wizard |
| `pointers-dns.js` | DNS pointers tab, cached list loaders |
| `emails-list.js` | Mailbox list table, search, pagination, client setup modal hooks |
| `emails-actions.js` | Create, edit, delete mailbox actions, mail client settings |
| `emails-import.js` | CSV mailbox bulk import/export and progress UI |
| `fleet-health.js` | Dashboard fleet overview across all domains |
| `forwarders-spam.js` | Forwarders and spam filter UI |
| `delegations.js` | Admin delegations page |
| `api-tokens.js` | API token create/list/revoke UI |
| `init.js` | `DOMContentLoaded` wiring, tab loaders, global event listeners |
| `theme-smtp.js` | Theme picker and SMTP settings panel |
| `notifications-render.js` | Notification settings form rendering |
| `notifications-actions.js` | Notification target CRUD and test send |
| `logs.js` | Audit log viewer |

`init.js` is intentionally late: it attaches listeners that call functions defined in the feature scripts above.

## Naming

File names describe the feature area, not load position. Order is documented here and enforced in `index.html`, not by numeric prefixes.

`api-cache.js` is named to avoid confusion with `static/js/cache.js`, the ES module that supplies TTL helpers on `window.Mxm.cache`.

## Adding a new script

1. Pick a descriptive name (`feature-area.js`).
2. Decide where it belongs in the table above based on what globals it defines and what it calls.
3. Add a `<script defer>` tag in `templates/index.html` at that position.
4. Add a row to the table in this document.
5. Keep each file under roughly 400 lines. Split by sub-feature if it grows.

## Related docs

- [Testing](testing.md) for which JS is covered by Node unit tests vs manual UI checks.
