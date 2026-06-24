let fleetDomainsLoading = false;

function fleetDomainAccessible(domain) {
    if (!domain) return false;
    if (currentUser?.is_admin) return true;
    return (
        userHasPermission("dashboard", domain)
        || userHasPermission("dns", domain)
        || userHasPermission("emails", domain)
    );
}

function formatFleetLastUpdated(ts) {
    if (!ts) return "Not scanned yet — use Refresh fleet to scan now.";
    const ageSec = Math.max(0, Math.floor(Date.now() / 1000 - Number(ts)));
    if (ageSec < 60) return "Updated just now.";
    if (ageSec < 3600) {
        const mins = Math.floor(ageSec / 60);
        return `Updated ${mins} minute${mins === 1 ? "" : "s"} ago.`;
    }
    const hours = Math.floor(ageSec / 3600);
    return `Updated ${hours} hour${hours === 1 ? "" : "s"} ago.`;
}

function updateFleetHealthMeta(lastRunAt) {
    const meta = document.getElementById("fleet-health-meta");
    if (!meta) return;
    meta.textContent = `Mail routing, DNS health, and mailbox counts across all domains you can access. ${formatFleetLastUpdated(lastRunAt)}`;
}

function renderFleetHealthPlaceholder(message) {
    const tbody = document.getElementById("fleet-health-tbody");
    if (!tbody) return;
    setTrustedHtml(tbody, tablePlaceholderRowHtml(4, message));
}

function renderFleetHealthRows(rows) {
    const tbody = document.getElementById("fleet-health-tbody");
    const card = document.getElementById("fleet-health-card");
    if (!tbody) return;

    if (!rows.length) {
        renderFleetHealthPlaceholder("No domains to show.");
        return;
    }

    setTrustedHtml(tbody, "");
    rows.forEach((row) => {
        const tr = document.createElement("tr");
        tr.dataset.domain = row.domain;
        tr.style.cursor = "pointer";
        tr.title = `Switch to ${row.domain}`;
        tr.innerHTML = `
            <td><strong>${escapeHtml(row.domain)}</strong></td>
            <td>${row.mailHtml}</td>
            <td>${row.dnsHtml}</td>
            <td style="text-align: right;">${escapeHtml(row.mailboxCount)}</td>
        `;
        tbody.appendChild(tr);
    });
    if (card) card.dataset.loaded = "true";
}

async function loadFleetHealth({ force = false } = {}) {
    const card = document.getElementById("fleet-health-card");
    if (!card || fleetDomainsLoading) {
        return;
    }

    fleetDomainsLoading = true;
    const firstLoad = card.dataset.loaded !== "true";
    card.style.display = "";

    if (firstLoad && !force) {
        renderFleetHealthPlaceholder("Loading fleet status...");
    }

    try {
        setElementRefreshing(card, force);
        const payload = await hydrateDomainRowsFromFleet({ force, paint: true });
        const domains = (payload.domains || []).filter((entry) => fleetDomainAccessible(entry.domain));

        if (domains.length < 2) {
            card.style.display = "none";
            return;
        }

        updateFleetHealthMeta(payload.last_run_at);
        const rows = domains.map((entry) => fleetTableRowFromEntry(entry));
        rows.sort((a, b) => a.domain.localeCompare(b.domain));
        renderFleetHealthRows(rows);
    } catch (err) {
        console.warn("Fleet health load failed:", err);
        if (firstLoad || force) {
            renderFleetHealthPlaceholder("Could not load fleet status.");
        }
    } finally {
        setElementRefreshing(card, false);
        fleetDomainsLoading = false;
    }
}

function initFleetHealthTable() {
    const tbody = document.getElementById("fleet-health-tbody");
    if (!tbody || tbody.dataset.clickInit === "true") {
        return;
    }
    tbody.dataset.clickInit = "true";
    tbody.addEventListener("click", (event) => {
        const row = event.target.closest("tr[data-domain]");
        if (!row?.dataset.domain) return;
        const domain = row.dataset.domain;
        const select = document.getElementById("global-domain-select");
        if (select) {
            select.value = domain;
            select.dispatchEvent(new Event("change"));
        }
    });
}

document.getElementById("btn-refresh-fleet-health")?.addEventListener("click", async () => {
    const btn = document.getElementById("btn-refresh-fleet-health");
    if (btn) {
        btn.disabled = true;
        setTrustedHtml(btn, btnLabel("arrow-clockwise", "Refreshing...", true));
    }
    try {
        await loadFleetHealth({ force: true });
        const card = document.getElementById("fleet-health-card");
        if (card?.style.display === "none") {
            showAlert("info", "Fleet overview appears when you have two or more domains.");
        } else {
            showAlert("success", "Fleet status refreshed.");
        }
    } catch (err) {
        showAlert("error", err.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            setTrustedHtml(btn, btnLabel("arrow-clockwise", "Refresh fleet"));
        }
    }
});

initFleetHealthTable();
