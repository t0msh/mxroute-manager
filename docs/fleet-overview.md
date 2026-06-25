# Fleet overview

When you have more than one domain on your MXroute account, squinting at the dashboard one domain at a time gets old fast. **Fleet overview** is the table that shows the whole account at once: mail routing, DNS health, and mailbox counts per domain.

## Where to find it

- **Dashboard** tab: fleet table appears when you have two or more domains visible to your user.
- **Domains** tab: **Active Domains** list shares the same cached data for row badges and quick health context.

Click a fleet row to switch the global domain selector to that domain.

## What each row shows

| Column | Meaning |
| --- | --- |
| Domain | Domain name |
| Mail | Whether mail hosting is enabled and routing looks sane |
| DNS | Latest cached public DNS health (healthy / degraded / unhealthy) |
| Mailboxes | Count of mailboxes on the domain |

Exact labels and badges match what you see on the dashboard DNS health cards, but aggregated for every domain in one view. For what **healthy**, **degraded**, and **unhealthy** mean per record, see [DNS health checks](dns-health.md).

## How fresh is the data?

Fleet overview is **cached in the database**, not recomputed on every page load. A background job refreshes it on a schedule (every 15 minutes) and on app startup. Admins can force a refresh from the UI when available.

API:

```bash
# Read cached fleet state
curl -sS -H "Authorization: Bearer $MXM_TOKEN" \
  https://manager.example.com/api/fleet/overview

# Force rescan (admin or users with dashboard/dns on domains)
curl -sS -X POST -H "Authorization: Bearer $MXM_TOKEN" \
  https://manager.example.com/api/fleet/overview/refresh
```

Delegated users only see domains they are granted access to. Admins see the full MXroute account list.

## Related guides

| Guide | Topic |
| --- | --- |
| [App tour - Dashboard](app-tour.md#dashboard) | Screenshots |
| [Notifications](notifications.md#dns-health-monitoring) | Alerts when DNS goes bad |
| [Adding a domain](adding-a-domain.md) | Per-domain DNS wizard |
| [DNS health checks](dns-health.md) | Checklist rules and custom SPF/DMARC |
