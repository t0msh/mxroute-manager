import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
    dnsNeedsFix,
    escapeHtml,
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
    it("formats all credential lines", () => {
        const text = formatMailboxCredentialsText({
            email: "u@example.com",
            password: "secret",
            imapHost: "imap.example.com",
            smtpHost: "smtp.example.com",
            webmailUrl: "https://webmail.example.com",
        });
        assert.match(text, /Username \(Email\): u@example\.com/);
        assert.match(text, /Password: secret/);
        assert.match(text, /IMAP Hostname: imap\.example\.com/);
        assert.match(text, /SMTP Hostname: smtp\.example\.com/);
        assert.match(text, /Webmail Link: https:\/\/webmail\.example\.com/);
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
