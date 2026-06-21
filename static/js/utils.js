/** Shared string/DNS display helpers (pure, no DOM). */

export const DNS_CHECK_SHORT = {
    mx: "MX",
    spf: "SPF",
    dkim: "DKIM",
    dmarc: "DMARC",
    verification: "Verify",
    webmail: "Webmail",
};

export function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

/** JSON string safe for double-quoted HTML onclick attributes. */
export function jsAttrString(value) {
    return escapeHtml(JSON.stringify(String(value ?? "")));
}

export function formatMailboxCredentialsText(creds) {
    return [
        `Username (Email): ${creds.email}`,
        `Password: ${creds.password}`,
        `IMAP Hostname: ${creds.imapHost} (Port 993, SSL/TLS)`,
        `SMTP Hostname: ${creds.smtpHost} (Port 465, SSL/TLS)`,
        `Webmail Link: ${creds.webmailUrl}`,
    ].join("\n");
}

export function dnsNeedsFix(health) {
    return !!health && health.overall !== "healthy";
}

/** Run async fn over items with a fixed concurrency cap (third-party / heavy API calls). */
export async function mapWithConcurrency(items, limit, fn) {
    const results = new Array(items.length);
    let i = 0;
    async function worker() {
        while (i < items.length) {
            const idx = i++;
            results[idx] = await fn(items[idx], idx);
        }
    }
    await Promise.all(
        Array.from({ length: Math.min(limit, items.length) }, () => worker())
    );
    return results;
}

export function renderDnsStatusBadge(health) {
    if (!health || !health.checks) {
        return `<span style="color: var(--color-muted); font-size: 0.85rem;">Unknown</span>`;
    }
    const failing = Object.entries(health.checks)
        .filter(([, check]) => check.status === "warn" || check.status === "fail")
        .map(([key]) => DNS_CHECK_SHORT[key] || key);
    const pending = Object.entries(health.checks)
        .filter(([, check]) => check.status === "pending")
        .map(([key]) => DNS_CHECK_SHORT[key] || key);

    if (health.overall === "healthy") {
        return `<span class="status-indicator success"><span class="dot"></span> All OK</span>`;
    }
    if (failing.length > 0) {
        const level = health.overall === "unhealthy" ? "danger" : "warning";
        return `<span class="status-indicator ${level}"><span class="dot"></span> ${escapeHtml(failing.join(" · "))}</span>`;
    }
    if (pending.length > 0) {
        return `<span class="status-indicator warning"><span class="dot"></span> Pending</span>`;
    }
    return `<span class="status-indicator warning"><span class="dot"></span> Degraded</span>`;
}
