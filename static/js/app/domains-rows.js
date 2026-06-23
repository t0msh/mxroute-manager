async function refreshDomainRowDetails(domain, { force = false } = {}) {
    const safeId = domain.replace(/[^a-zA-Z0-9-]/g, "-");
    const mailCell = document.getElementById(`domain-mail-${safeId}`);
    const dnsCell = document.getElementById(`domain-dns-${safeId}`);
    if (!mailCell || !dnsCell) return;

    const detailsUrl = `/api/domains/${domain}`;
    const healthUrl = `/api/domains/${domain}/dns/setup-health`;
    const rowCached = domainRowCache.get(domain);

    if (rowCached) {
        setTrustedHtml(mailCell, rowCached.mailHtml);
        setTrustedHtml(dnsCell, rowCached.dnsHtml);
        renderDomainActionsCell(domain);
    }

    const needsRefresh = force || !isCacheFresh(detailsUrl) || !isCacheFresh(healthUrl);
    if (!needsRefresh) return;

    const applyFromCache = () => {
        const dEntry = apiCache.get(detailsUrl);
        const hEntry = apiCache.get(healthUrl);
        if (dEntry?.data || hEntry?.data) {
            applyDomainRowDetails(domain, dEntry?.data, hEntry?.data);
        }
    };

    try {
        await Promise.all([
            cachedFetch(detailsUrl, {
                force,
                onRefreshStart: () => setCellRefreshing(mailCell, true),
                onRefreshEnd: () => setCellRefreshing(mailCell, false),
                onUpdated: applyFromCache,
            }),
            cachedFetch(healthUrl, {
                force,
                onRefreshStart: () => setCellRefreshing(dnsCell, true),
                onRefreshEnd: () => setCellRefreshing(dnsCell, false),
                onUpdated: applyFromCache,
            }),
        ]);
        applyFromCache();
    } catch (err) {
        setCellRefreshing(mailCell, false);
        setCellRefreshing(dnsCell, false);
    }
}

function renderDomainsTableRows(domains) {
    const tbody = document.getElementById("domains-list-tbody");
    setTrustedHtml(tbody, "");
    domains.forEach(domain => {
        const safeId = domain.replace(/[^a-zA-Z0-9-]/g, "-");
        const cached = domainRowCache.get(domain);
        const tr = document.createElement("tr");
        tr.dataset.domain = domain;
        tr.innerHTML = `
            <td><strong>${escapeHtml(domain)}</strong></td>
            <td id="domain-mail-${safeId}">${cached?.mailHtml || `<span style="color: var(--color-muted); font-size: 0.85rem;">—</span>`}</td>
            <td id="domain-dns-${safeId}">${cached?.dnsHtml || `<span style="color: var(--color-muted); font-size: 0.85rem;">—</span>`}</td>
            <td style="text-align: right;" id="domain-actions-${safeId}"></td>
        `;
        tbody.appendChild(tr);
        renderDomainActionsCell(domain);
    });
}

async function refreshDomainsListStatus() {
    const tbody = document.getElementById("domains-list-tbody");
    const domains = [...tbody.querySelectorAll("tr[data-domain]")].map(row => row.dataset.domain);
    if (!domains.length) {
        showAlert("warning", "No domains to refresh.");
        return;
    }
    const btn = document.getElementById("btn-refresh-domains-status");
    if (btn) {
        btn.disabled = true;
        setTrustedHtml(btn, btnLabel("arrow-clockwise", "Refreshing...", true));
    }
    try {
        await window.Mxm.utils.mapWithConcurrency(
            domains,
            5,
            (domain) => refreshDomainRowDetails(domain, { force: true })
        );
        showAlert("success", "Domain mail and DNS status refreshed.");
    } catch (err) {
        showAlert("error", err.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            setTrustedHtml(btn, btnLabel("arrow-clockwise", "Refresh status"));
        }
    }
}

async function loadDomainsList({ force = false } = {}) {
    const tbody = document.getElementById("domains-list-tbody");
    const card = document.getElementById("domains-list-card");
    const hasRows = !!tbody.querySelector("tr[data-domain]");
    const firstLoad = !hasRows;

    if (firstLoad) {
        setTrustedHtml(tbody, loadingRowHtml(4, "Querying domains..."));
    }

    try {
        const result = await cachedFetch("/api/domains", {
            force,
            onRefreshStart: () => setElementRefreshing(card, true),
            onRefreshEnd: () => setElementRefreshing(card, false),
            onUpdated: (updated) => {
                if (updated?.success && updated.data?.length) {
                    const existing = [...tbody.querySelectorAll("tr[data-domain]")].map(r => r.dataset.domain);
                    const sameList = existing.length === updated.data.length
                        && updated.data.every(d => existing.includes(d));
                    if (!sameList) renderDomainsTableRows(updated.data);
                }
            },
        });

        if (!result.success || !result.data || result.data.length === 0) {
            setTrustedHtml(tbody, '<tr><td colspan="4" style="text-align: center; color: var(--color-muted);">No domains found on this account.</td></tr>');
            return;
        }

        const domains = result.data;
        const existingDomains = [...tbody.querySelectorAll("tr[data-domain]")].map(r => r.dataset.domain);
        const sameList = hasRows
            && existingDomains.length === domains.length
            && domains.every(d => existingDomains.includes(d));

        if (!sameList) {
            renderDomainsTableRows(domains);
        }
        prefetchDomainsListStatus(domains);
    } catch (err) {
        if (firstLoad || !hasRows) {
            setTrustedHtml(tbody, `<tr><td colspan="4" style="text-align: center; color: var(--danger); font-weight: 500;">Failed to load domains: ${escapeHtml(err.message)}</td></tr>`);
        } else {
            showAlert("error", `Failed to refresh domains: ${err.message}`);
        }
    }
}

