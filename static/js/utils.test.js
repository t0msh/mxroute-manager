import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
    dnsNeedsFix,
    escapeHtml,
    formatAuditLogDetailsHtml,
    formatMailboxCredentialsText,
    jsAttrString,
    renderDnsStatusBadge,
} from "./utils.js";

describe("escapeHtml", () => {
    it("escapes HTML special characters", () => {
        assert.equal(escapeHtml(`<a href="x">&'`), "&lt;a href=&quot;x&quot;&gt;&amp;&#39;");
    });

    it("handles nullish values", () => {
        assert.equal(escapeHtml(null), "");
    });
});

describe("jsAttrString", () => {
    it("JSON-encodes then escapes for onclick attributes", () => {
        assert.equal(jsAttrString(`he said "hi"`), "&quot;he said \\&quot;hi\\&quot;&quot;");
    });
});

describe("formatMailboxCredentialsText", () => {
    const settings = {
        imap: { host: "mail.example.com", port: 993, encryption: "ssl" },
        smtp_ssl: { host: "mail.example.com", port: 465, encryption: "ssl" },
        smtp_starttls: { host: "mail.example.com", port: 587, encryption: "starttls" },
        webmail: { url: "https://webmail.example.com", status: "pass" },
        username_note: "Use your full email address as the username.",
    };

    it("formats all credential lines", () => {
        const text = formatMailboxCredentialsText({
            email: "u@example.com",
            password: "secret",
            settings,
        });
        assert.match(text, /Email address: u@example\.com/);
        assert.match(text, /Password: secret/);
        assert.match(text, /IMAP \(incoming mail\)/);
        assert.match(text, /Server: mail\.example\.com/);
        assert.match(text, /Port: 587/);
        assert.match(text, /Webmail: https:\/\/webmail\.example\.com/);
    });

    it("omits password and webmail when absent", () => {
        const text = formatMailboxCredentialsText({
            email: "u@example.com",
            settings: {
                ...settings,
                webmail: { url: null, status: "skipped" },
            },
        });
        assert.doesNotMatch(text, /Password:/);
        assert.doesNotMatch(text, /Webmail:/);
    });
});

describe("formatAuditLogDetailsHtml", () => {
    it("renders key-value pairs instead of raw JSON", () => {
        const html = formatAuditLogDetailsHtml({ recovery_email: "a@b.com", outcome: "updated" });
        assert.match(html, /Recovery Email:/);
        assert.match(html, /a@b\.com/);
        assert.match(html, /Outcome:/);
        assert.match(html, /updated/);
        assert.doesNotMatch(html, /\{/);
    });

    it("shows em dash for empty details", () => {
        const html = formatAuditLogDetailsHtml({});
        assert.match(html, /—/);
    });
});

describe("dnsNeedsFix", () => {
    it("is false for healthy overall", () => {
        assert.equal(dnsNeedsFix({ overall: "healthy" }), false);
    });

    it("is true for degraded or unhealthy", () => {
        assert.equal(dnsNeedsFix({ overall: "degraded" }), true);
        assert.equal(dnsNeedsFix({ overall: "unhealthy" }), true);
    });
});

describe("renderDnsStatusBadge", () => {
    it("returns Unknown when health missing", () => {
        assert.match(renderDnsStatusBadge(null), /Unknown/);
    });

    it("shows All OK when healthy", () => {
        assert.match(
            renderDnsStatusBadge({
                overall: "healthy",
                checks: { mx: { status: "pass" } },
            }),
            /All OK/
        );
    });

    it("escapes failing check labels", () => {
        const html = renderDnsStatusBadge({
            overall: "unhealthy",
            checks: {
                mx: { status: "fail" },
                spf: { status: "warn" },
            },
        });
        assert.match(html, /MX/);
        assert.match(html, /SPF/);
        assert.doesNotMatch(html, /<script/);
    });

    it("shows Pending when only pending checks remain", () => {
        assert.match(
            renderDnsStatusBadge({
                overall: "degraded",
                checks: { dkim: { status: "pending" } },
            }),
            /Pending/
        );
    });
});
