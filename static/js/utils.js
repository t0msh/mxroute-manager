/** Shared string/DNS display helpers (pure, no DOM). */

export const DNS_CHECK_SHORT = {
    mail: "Mail",
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

export function formatMailboxCredentialsText({ email, password, settings }) {
    const lines = [`Email address: ${email}`];
    if (password) {
        lines.push(`Password: ${password}`);
    }
    lines.push(
        "",
        "IMAP (incoming mail)",
        `  Server: ${settings.imap.host}`,
        `  Port: ${settings.imap.port}`,
        "  Encryption: SSL/TLS",
        "",
        "SMTP (outgoing mail) — SSL",
        `  Server: ${settings.smtp_ssl.host}`,
        `  Port: ${settings.smtp_ssl.port}`,
        "  Encryption: SSL/TLS",
        "",
        "SMTP (outgoing mail) — STARTTLS",
        `  Server: ${settings.smtp_starttls.host}`,
        `  Port: ${settings.smtp_starttls.port}`,
        "  Encryption: STARTTLS",
    );
    if (settings.webmail?.url) {
        lines.push("", `Webmail: ${settings.webmail.url}`);
        if (settings.webmail.status === "pending") {
            lines.push("  (DNS may still be propagating)");
        }
    }
    lines.push("", settings.username_note || "Use your full email address as the username.");
    return lines.join("\n");
}

function formatAuditDetailValue(value) {
    if (value === null || value === undefined) return "—";
    if (Array.isArray(value)) {
        return value.map((item) => (typeof item === "object" ? JSON.stringify(item) : String(item))).join(", ");
    }
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
}

function formatAuditDetailLabel(key) {
    return String(key)
        .replace(/_/g, " ")
        .replace(/\b\w/g, (char) => char.toUpperCase());
}

/** Human-readable audit log details for table display. */
export function formatAuditLogDetailsHtml(details) {
    if (details === null || details === undefined) {
        return '<span style="color: var(--color-muted);">—</span>';
    }
    if (typeof details !== "object" || Array.isArray(details)) {
        return `<span>${escapeHtml(formatAuditDetailValue(details))}</span>`;
    }
    const entries = Object.entries(details);
    if (!entries.length) {
        return '<span style="color: var(--color-muted);">—</span>';
    }
    const rows = entries.map(([key, value]) => {
        const label = formatAuditDetailLabel(key);
        const display = formatAuditDetailValue(value);
        return `<div><span style="color: var(--color-muted);">${escapeHtml(label)}:</span> ${escapeHtml(display)}</div>`;
    }).join("");
    return `<div style="font-size: 0.75rem; line-height: 1.45; color: var(--color-secondary); max-width: 500px;">${rows}</div>`;
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
