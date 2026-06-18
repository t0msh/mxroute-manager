import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { CACHE_TTL_MS, getCacheTtl, isCacheFresh } from "./cache.js";

describe("getCacheTtl", () => {
    it("picks TTL by URL pattern", () => {
        assert.equal(getCacheTtl("/api/domains"), CACHE_TTL_MS.domains);
        assert.equal(getCacheTtl("/api/quota"), CACHE_TTL_MS.quota);
        assert.equal(getCacheTtl("/api/domains/foo/dns/health"), CACHE_TTL_MS.dnsHealth);
        assert.equal(getCacheTtl("/api/domains/foo/dns/setup-health"), CACHE_TTL_MS.dnsHealth);
        assert.equal(getCacheTtl("/api/domains/foo/dns"), CACHE_TTL_MS.dnsRecords);
        assert.equal(getCacheTtl("/api/domains/foo.com"), CACHE_TTL_MS.domainDetail);
        assert.equal(getCacheTtl("/api/emails"), CACHE_TTL_MS.list);
    });
});

describe("isCacheFresh", () => {
    it("is false without an entry", () => {
        assert.equal(isCacheFresh(null, 60_000, 1_000_000), false);
    });

    it("is true inside TTL window", () => {
        const now = 1_000_000;
        const entry = { fetchedAt: now - 30_000 };
        assert.equal(isCacheFresh(entry, 60_000, now), true);
    });

    it("is false when stale", () => {
        const now = 1_000_000;
        const entry = { fetchedAt: now - 90_000 };
        assert.equal(isCacheFresh(entry, 60_000, now), false);
    });
});
