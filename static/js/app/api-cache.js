function getCacheTtl(url) {
    return window.Mxm.cache.getCacheTtl(url);
}

function isCacheFresh(url) {
    return window.Mxm.cache.isCacheFresh(apiCache.get(url), getCacheTtl(url));
}

function invalidateApiCache(urlPrefix) {
    for (const key of [...apiCache.keys()]) {
        if (key.startsWith(urlPrefix)) apiCache.delete(key);
    }
    if (urlPrefix === "/api/domains") domainRowCache.clear();
}

function invalidateDomainCache(domain) {
    // Domains are validated to simple hostnames, so URL building never encodes them
    // differently; a single raw prefix covers every per-domain cache key.
    invalidateApiCache(`/api/domains/${domain}`);
    domainRowCache.delete(domain);
}

function setElementRefreshing(elOrId, refreshing) {
    const el = typeof elOrId === "string" ? document.getElementById(elOrId) : elOrId;
    if (!el) return;
    el.classList.toggle("is-refreshing", refreshing);
    let indicator = el.querySelector(".refresh-indicator");
    if (refreshing) {
        if (!indicator) {
            indicator = document.createElement("span");
            indicator.className = "refresh-indicator";
            indicator.title = "Updating…";
            const anchor = el.querySelector(".card-title") || el.querySelector(".stat-card-header") || el;
            anchor.appendChild(indicator);
        }
    } else if (indicator) {
        indicator.remove();
    }
}

function setCellRefreshing(cellEl, refreshing) {
    if (!cellEl) return;
    cellEl.classList.toggle("is-refreshing", refreshing);
    let indicator = cellEl.querySelector(".refresh-indicator");
    if (refreshing) {
        if (!indicator) {
            indicator = document.createElement("span");
            indicator.className = "refresh-indicator refresh-indicator-inline";
            indicator.title = "Updating…";
            cellEl.appendChild(indicator);
        }
    } else if (indicator) {
        indicator.remove();
    }
}

function setSidebarQuotaRefreshing(refreshing) {
    const barTrack = document.querySelector("#sidebar-quota-container .quota-bar");
    if (!barTrack) return;
    barTrack.classList.toggle("is-refreshing", refreshing);
    barTrack.setAttribute("aria-busy", refreshing ? "true" : "false");
}

// Shared skeleton for table loaders: loading placeholder -> cachedFetch (with
// refresh indicator + background revalidation) -> render -> error row. Each caller
// supplies its own firstLoad heuristic, render fn, and placeholder/error markup.
async function fetchCachedList(options) {
    const { url, tbody, card, force, firstLoad, render, loadingHtml, errorHtml } = options;
    if (firstLoad) setTrustedHtml(tbody, loadingHtml);
    try {
        const result = await cachedFetch(url, {
            force,
            onRefreshStart: () => setElementRefreshing(card, true),
            onRefreshEnd: () => setElementRefreshing(card, false),
            onUpdated: render,
        });
        render(result);
    } catch (err) {
        if (firstLoad) {
            setTrustedHtml(tbody, typeof errorHtml === "function" ? errorHtml(err) : errorHtml);
        }
    }
}

async function cachedFetch(url, options = {}) {
    const { force = false, onRefreshStart, onRefreshEnd, onUpdated } = options;
    const ttl = getCacheTtl(url);
    const entry = apiCache.get(url);
    const now = Date.now();

    const storeAndReturn = (data) => {
        apiCache.set(url, { data, fetchedAt: Date.now() });
        return data;
    };

    if (entry && !force) {
        const age = now - entry.fetchedAt;
        if (age < ttl) {
            return entry.data;
        }

        if (!backgroundRefreshes.has(url)) {
            onRefreshStart?.();
            const refreshPromise = apiRequest(url)
                .then((data) => {
                    storeAndReturn(data);
                    onUpdated?.(data);
                    return data;
                })
                .catch((err) => console.warn(`Background refresh failed for ${url}:`, err))
                .finally(() => {
                    backgroundRefreshes.delete(url);
                    onRefreshEnd?.();
                });
            backgroundRefreshes.set(url, refreshPromise);
        }
        return entry.data;
    }

    onRefreshStart?.();
    try {
        const data = await apiRequest(url);
        return storeAndReturn(data);
    } finally {
        onRefreshEnd?.();
    }
}

function setSettingsBoolToggle(id, value) {
    const el = document.getElementById(id);
    if (el) el.checked = value === true || value === "true";
}

function getSettingsBoolToggle(id) {
    return document.getElementById(id)?.checked ? "true" : "false";
}

function hasLoadedContent(el) {
    if (!el) return false;
    if (el.dataset.loaded === "true") return true;
    if (el.id === "domains-list-tbody") return !!el.querySelector("tr[data-domain]");
    if (el.id === "dns-health-checks") return el.children.length > 0;
    return el.textContent.trim() !== "" && el.textContent.trim() !== "--";
}

