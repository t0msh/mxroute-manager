# Bulk mailbox CSV import and export

Move mailboxes in and out without clicking through the UI one at a time. The CSV format is the same for both directions so you can export, edit in a spreadsheet, and import again.

## Where to find it

Open **Email Accounts** for the domain you want, then use **Import CSV** or **Export CSV** above the Active Mailboxes table.

Import opens a modal with preview. Export downloads the full mailbox list for the active domain (all mailboxes, not just the current table page).

## CSV columns

| Column | Required | Notes |
| --- | --- | --- |
| `username` | Yes | Local part only, or use `email` / `mailbox` / `address` with a full address |
| `password` | For import | Leave blank to auto-generate when the checkbox is enabled |
| `quota` | No | Megabytes. Defaults to the app standard if omitted |
| `limit` | No | Daily send limit. Defaults to the app standard if omitted |
| `recovery_email` | No | Enables self-service password reset for that mailbox |
| `domain` | No | Omit when importing into the active domain; include for multi-domain batches |

Header row example:

```csv
username,password,quota,limit,recovery_email,domain
alice,Abcd1234!,1024,9600,alice.personal@gmail.com,example.com
bob,,1024,9600,,example.com
```

## Import workflow

1. Choose a CSV file (themed **Browse** button, not the browser default).
2. Optionally enable **Generate secure passwords** for blank password cells.
3. Click **Preview import**. The app validates each row and flags:
   - invalid usernames or passwords
   - duplicates within the CSV
   - mailboxes that already exist (checked against Active Mailboxes, no extra MXroute round trip)
4. Confirm and run. Creation is rate-limited (3 parallel requests) with a progress card and downloadable results CSV.

Rows marked **Already exists** are skipped. Fix the CSV or remove those rows before starting.

## Export workflow

1. Load the domain in **Email Accounts** (the list must be populated).
2. Click **Export CSV**.

Passwords are always blank on export. MXroute does not expose them after creation. To re-import the same users with new passwords, leave the password column empty and use generated passwords, or fill passwords in your spreadsheet before import.

Recovery emails are included when configured in the app database.

## Round-tripping

Typical loop:

1. Export `example.com` mailboxes.
2. Edit quotas or add rows in Excel / LibreOffice / vim, your call.
3. Import the updated file with preview.
4. Export again to verify.

Because passwords are not exported, treat export files as non-secret configuration data, not credential backups.

## API

Automation can validate rows before create:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $MXM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"default_domain":"example.com","existing_by_domain":{"example.com":["alice"]},"rows":[{"username":"bob","password":"Abcd123!"}]}' \
  https://manager.example.com/api/email-accounts/import/preview
```

Creation still uses `POST /api/domains/<domain>/email-accounts` per mailbox. See [HTTP API](api.md).

## Related guides

| Guide | Topic |
| --- | --- |
| [App tour](app-tour.md) | Email Accounts tab screenshots |
| [HTTP API](api.md) | Tokens and scripting |
| [Notifications](notifications.md) | Alerts when mailboxes hit quota or send thresholds |
