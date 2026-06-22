/** API cache TTL helpers (pure, no Map globals). */

export const CACHE_TTL_MS = {
    domains: 2 * 60 * 1000,
    domainDetail: 60 * 1000,
    dnsRecords: 5 * 60 * 1000,
    dnsHealth: 5 * 60 * 1000,
    quota: 90 * 1000,
    list: 60 * 1000,
};

export function getCacheTtl(url, ttlMs = CACHE_TTL_MS) {
    if (url === "/api/domains") return ttlMs.domains;
    if (url === "/api/quota") return ttlMs.quota;
    if (/\/dns\/health/.test(url) || /\/dns\/setup-health/.test(url)) return ttlMs.dnsHealth;
    if (/\/dns$/.test(url.split("?")[0])) return ttlMs.dnsRecords;
    if (/^\/api\/domains\/[^/]+$/.test(url.split("?")[0])) return ttlMs.domainDetail;
    return ttlMs.list;
}

export function isCacheFresh(entry, ttlMs, now = Date.now()) {
    if (!entry) return false;
    return now - entry.fetchedAt < ttlMs;
}
