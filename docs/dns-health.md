# DNS health checks

MXroute Manager compares **live public DNS** (what the internet sees) against what MXroute expects for mail on each domain. That checklist powers the **Dashboard** DNS card, the domain wizard, the **Active Domains** table, **Fleet overview**, and optional [DNS health monitoring](notifications.md#dns-health-monitoring).

This is not a full deliverability audit. It answers a narrower question: *"Are the MXroute mail records present and sane for this domain?"*

Cloudflare is optional for **reading** health (public lookups work without it). Cloudflare **is** required for one-click deploy, the wizard, and **Fix DNS entries** in the Actions menu.

## Overall status

| Status | Meaning |
| --- | --- |
| **Healthy** | Every required check passed. Mail DNS looks good from MXroute's point of view. |
| **Degraded** | Required records are in place, but something optional or informational wants attention (for example DKIM propagation, DMARC differing from your default template, or webmail CNAME still propagating). |
| **Unhealthy** | A required record is missing or wrong (usually MX or SPF). |

When **mail hosting is disabled** for a domain, MX/SPF/DKIM/DMARC checks are skipped and do not affect the overall score. Verification TXT is still evaluated when MXroute provides one.

## What each check does

Checks query public resolvers (same idea as `dig` against Google or Cloudflare DNS). Expected values for MX, SPF, and DKIM come from the **MXroute API** for that domain. DMARC uses your configured template (see below).

| Check | Required? | Pass condition (summary) |
| --- | --- | --- |
| **MX Records** | Yes | Live MX hostnames and priorities match MXroute exactly. |
| **SPF (TXT)** | Yes | A `v=spf1` record at the domain root includes every `include:` mechanism MXroute expects (typically `include:mxroute.com`). Extra senders (Mailgun, SES, etc.) are fine. |
| **DKIM (TXT)** | No (warn) | The `x._domainkey` TXT public key matches MXroute's key for the domain. |
| **DMARC (TXT)** | No (warn) | See [DMARC policy](#dmarc-policy-default-and-per-domain) below. |
| **Domain Verification (TXT)** | No (warn) | MXroute's verification TXT is present when the API provides one. |
| **Webmail (CNAME)** | Optional | Only shown when Cloudflare is configured and `webmail.<domain>` was deployed. Never fails overall health. |

### MX

MXroute usually publishes two MX records (primary and relay). The checker expects an **exact** match on priority and hostname. If you hand-edit MX at your DNS host, keep the pair MXroute gives you.

### SPF

MXroute ships a canonical SPF like `v=spf1 include:mxroute.com -all`. The wizard deploys that string when you click **Deploy All Records** or **Fix DNS entries**.

**Health checks are relaxed:** if your live SPF is a **superset** (same MXroute includes plus Mailgun, Amazon SES, SendGrid, and so on), the check **passes**. It only fails when a required `include:` from MXroute is missing.

This matches real multi-service setups. You do not need to strip third-party senders from SPF to get a green check.

### DKIM

MXroute generates per-domain DKIM on `x._domainkey.<domain>`. The checker compares the **public key** (`p=`), not the full TXT string, so minor formatting differences are fine.

A warn here is informational. Fix it when you want signing aligned with MXroute's current key (for example after re-registration).

### DMARC policy: default and per-domain

DMARC is the most variable record across domains. Marketing domains might stay on `p=none`; production mail might use `p=reject` with custom `rua` reporting addresses.

Two layers:

| Layer | Source | Used for |
| --- | --- | --- |
| **Global default** | `DMARC_RECORD` in `.env` | Wizard deploy, **Fix DNS** when no per-domain override exists, and the baseline for health comparison |
| **Per-domain override** (optional) | SQLite (`domain_dmarc_policies`) | That domain's deploy target and **exact** health match when set |

Configure the global default in [Configuration](configuration.md#dns-defaults). Per-domain overrides are set in the UI (below).

**Health logic:**

1. **Custom policy enabled for the domain** - live `_dmarc` TXT must match your stored policy (normalized). Mismatch = warn.
2. **No custom policy** - if live DNS matches the global default exactly, pass. If a valid `v=DMARC1` record exists but differs from the default (stricter `p=`, extra `rua`, etc.), **warn** with *"differs from default template"*. Missing record = warn.

So a domain with `p=reject` and custom reporting can show **degraded** (not unhealthy) until you either set a per-domain policy or accept the informational warn.

### Webmail

Optional `webmail.<domain>` CNAME to your `MX_SERVER` host. Skipped when not deployed; **pending** while public DNS catches up after Cloudflare deploy.

## Setting a per-domain DMARC policy

Use this when a domain's live DMARC should not match the global `DMARC_RECORD` template.

### During the wizard (Step 4)

1. Expand **Advanced DMARC (optional)**.
2. Check **Use custom DMARC policy for this domain**.
3. Paste the full DMARC TXT value (for example `v=DMARC1; p=reject; ...`).
4. Click **Deploy All Records**. The custom policy is saved before deploy so DMARC in Cloudflare matches your intent.

### On an existing domain

1. Open **Domains** → **Active Domains**.
2. Click **Actions** (⋮) on the row.
3. Choose **Edit DMARC policy**.
4. Enable **Use custom DMARC policy**, paste the value, **Save Policy**.

To revert to the global default, open the same modal, uncheck custom policy, and save (or clear the textarea and save).

Deploy and **Fix DNS entries** use the effective policy: custom if set, otherwise `DMARC_RECORD` from `.env`.

## Custom requirements (common cases)

| Your setup | What to expect | What to do |
| --- | --- | --- |
| SPF includes MXroute **and** Mailgun/SES/SendGrid | SPF **passes** | Nothing required for health. Keep one SPF TXT at the root. |
| Stricter DMARC (`p=reject`) with reporting URLs | Overall **degraded** (DMARC warn) unless custom policy set | **Edit DMARC policy** and paste your exact `_dmarc` TXT. |
| Multiple domains, different DMARC policies | Global `.env` cannot be the oracle for every zone | Set per-domain overrides where needed; keep `DMARC_RECORD` as the default for new/simple domains. |
| DNS managed outside Cloudflare | Health still works (public lookups) | Deploy records manually at your DNS host using values from MXroute / the wizard checklist. Fix buttons need Cloudflare. |
| Mail hosting disabled | Mail DNS checks skipped | Enable routing when you want mail DNS enforced again. |

## Fix DNS and deploy behaviour

**Fix DNS entries** (per domain) and **Fix unhealthy DNS** (bulk, admin) push missing or incorrect records to **Cloudflare** only. They are idempotent: correct records are skipped.

| Record | Deployed value |
| --- | --- |
| Verification | From MXroute verification API |
| MX / SPF / DKIM | From MXroute `/domains/<domain>/dns` |
| DMARC | Per-domain custom policy, or global `DMARC_RECORD` |
| Webmail | `webmail.<domain>` → `MX_SERVER` (when requested) |

**Important:** running **Fix DNS** on DMARC without a per-domain override overwrites `_dmarc` with the global template. If you run a stricter live policy, set **Edit DMARC policy** first (or leave DMARC out of the fix list when using the API).

## API

Read or update DMARC policy (requires `dns` on the domain, or admin):

```bash
# Current effective policy
curl -sS -H "Authorization: Bearer $MXM_TOKEN" \
  https://manager.example.com/api/domains/example.com/dmarc-policy

# Set custom policy
curl -sS -X PATCH -H "Authorization: Bearer $MXM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dmarc_record":"v=DMARC1; p=reject; sp=reject; aspf=r;"}' \
  https://manager.example.com/api/domains/example.com/dmarc-policy

# Clear custom policy (revert to global default)
curl -sS -X PATCH -H "Authorization: Bearer $MXM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dmarc_record":null}' \
  https://manager.example.com/api/domains/example.com/dmarc-policy
```

Full DNS health JSON: `GET /api/domains/<domain>/dns/health` (includes `dmarc_policy` metadata). See [HTTP API](api.md).

## Monitoring and fleet view

- **Fleet overview** caches the same overall status per domain. See [Fleet overview](fleet-overview.md).
- **Notifications → DNS health monitoring** can email or push when a domain flips between healthy and degraded/unhealthy. See [Notifications](notifications.md#dns-health-monitoring).

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| SPF fails but record "looks right" | Missing `include:mxroute.com` (or other MXroute include) | Add the MXroute include to your SPF TXT. |
| SPF passes, DMARC warn only | Valid DMARC that differs from `DMARC_RECORD` | Expected with custom policies. Set per-domain DMARC or ignore warn if mail is fine. |
| Everything failed after propagation delay | DNS not visible yet | Wait a few minutes, click **Recheck**. |
| Fix DNS reverted my DMARC | No per-domain override; fix deployed global template | Set **Edit DMARC policy** before fixing, or paste stricter value again. |
| Checks pass in UI, mail still bounces | Health only covers MXroute mail DNS | Check mailbox existence, routing toggle, and non-MXroute sending paths separately. |

## Related guides

| Guide | Topic |
| --- | --- |
| [Adding a domain](adding-a-domain.md) | Wizard steps and Actions menu |
| [Configuration](configuration.md) | `DMARC_RECORD` and Cloudflare env vars |
| [Fleet overview](fleet-overview.md) | Multi-domain DNS column |
| [Notifications](notifications.md) | Scheduled DNS alerts |
| [HTTP API](api.md) | `/dns/health`, `/dns/fix`, `/dmarc-policy` |
