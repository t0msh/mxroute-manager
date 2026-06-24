# Audit logs

Every interesting thing the app (or your users, or your scripts) does can leave a paper trail. **Audit Logs** is that trail: JSON lines on disk, browsable in the UI, downloadable when you need a spreadsheet or a compliance cosplay prop.

Administrators only. Delegated users never see this tab.

## What gets logged

Examples include:

- Sign-ins and failed auth
- Mailbox create, update, delete
- Domain and DNS changes
- Delegation and API token changes
- Spam list edits
- Settings updates
- Background monitor events (DNS health alerts, quota alerts)

Each entry has **timestamp** (UTC), **user** (email, username, or `system`), **action** (machine-readable key like `mailbox.create`), **target** (domain or mailbox), and **details** (JSON object with extra context).

Subscribed actions can also trigger [Apprise notifications](notifications.md).

## Using the Logs tab

| Control | Purpose |
| --- | --- |
| **Log Date** | Pick which daily log file to read (`YYYY-MM-DD.log` under `LOG_DIR`, default `./logs` in dev). |
| **Limit** | How many **most recent** entries to load into the table (50 to 500). Older entries in that day are not shown until you download the full file. |
| **Filter Table** | Client-side search across timestamp, user, action, target, and details JSON. |
| **Auto-refresh** | Poll every 10 seconds while you stay on the Logs tab. |
| **Reload Logs** | Fetch again with current date and limit. |
| **Download format** | CSV (spreadsheet) or JSONL (native on-disk format). |
| **Download** | Export the **entire selected day**, not just the rows in the table. |

### CSV vs JSONL

- **CSV** columns: `timestamp`, `user`, `action`, `target`, `details` (JSON string in the last column). Opens nicely in Excel or LibreOffice.
- **JSONL** is the raw log file: one JSON object per line, exactly as written.

Download via the API (admin session or admin-scoped Bearer token):

```bash
curl -sS -o audit-2026-06-24.csv \
  -H "Authorization: Bearer $MXM_ADMIN_TOKEN" \
  "https://manager.example.com/api/admin/logs/download?date=2026-06-24&format=csv"
```

Browser download from the UI uses the same endpoint with your logged-in session.

## Storage and retention

| Setting | Default | Notes |
| --- | --- | --- |
| `LOG_DIR` | `./logs` | In Docker, typically `/data/logs` on the volume |

The app appends to `LOG_DIR/YYYY-MM-DD.log`. It does not rotate or prune old files automatically. Back up `LOG_DIR` with your database, or ship logs to external storage if you need long retention.

## Related guides

| Guide | Topic |
| --- | --- |
| [Notifications](notifications.md) | Alert on audit events |
| [Access control](access-control.md) | Admin-only tab |
| [Configuration](configuration.md) | `LOG_DIR` variable |
| [HTTP API](api.md) | Actions performed via API tokens are logged too |
