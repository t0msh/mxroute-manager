// 5.4 Domain Pointers
async function loadPointersList(domain, { force = false } = {}) {
    const tbody = document.getElementById("pointers-tbody");
    const card = tbody?.closest(".glass-card");
    const firstLoad = !tbody.querySelector("tr[data-pointer]");

    const renderPointers = (result) => {
        setTrustedHtml(tbody, "");
        if (result?.success && result.data?.length > 0) {
            result.data.forEach(pointer => {
                const tr = document.createElement("tr");
                tr.dataset.pointer = pointer.pointer;
                tr.innerHTML = `
                    <td><strong>${escapeHtml(pointer.pointer)}</strong></td>
                    <td><span class="badge" style="font-size:0.75rem; padding:0.1rem 0.4rem; background:rgba(255,255,255,0.05); border: 1px solid var(--glass-border); border-radius:4px;">${escapeHtml(pointer.type)}</span></td>
                    <td style="text-align: right;">
                        ${actionMenuHtml([{ action: "delete", label: "Remove", icon: "trash", danger: true, dataset: { pointer: pointer.pointer } }])}
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            setTrustedHtml(tbody, '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">No pointers configured</td></tr>');
        }
    };

    await fetchCachedList({
        url: `/api/domains/${domain}/pointers`,
        tbody, card, force, firstLoad, render: renderPointers,
        loadingHtml: loadingRowHtml(3, "Loading pointers..."),
        errorHtml: '<tr><td colspan="3" style="text-align: center; color: var(--danger);">Failed to load pointers</td></tr>',
    });
}

// Add Pointer Modal Open
document.getElementById("btn-open-pointer-modal").addEventListener("click", () => {
    document.getElementById("pointer-name-input").value = "";
    openModal("modal-add-pointer");
});

document.getElementById("form-modal-create-pointer").addEventListener("submit", async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById("pointer-name-input");
    const typeSelect = document.getElementById("pointer-type-select");
    const pointer = nameInput.value.trim();
    const alias = typeSelect.value === "alias";
    
    if (!pointer) return;
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/pointers`, "POST", { pointer, alias });
        showAlert("success", `Pointer "${pointer}" created successfully.`);
        closeModal("modal-add-pointer");
        invalidateApiCache(`/api/domains/${activeDomain}/pointers`);
        invalidateDomainCache(activeDomain);
        await loadPointersList(activeDomain, { force: true });
        await loadDomainDetails(activeDomain, { force: true });
    } catch (err) {
        showAlert("error", err.message);
    }
});

async function handleDeletePointer(pointer) {
    const confirmed = await showConfirm({
        title: "Remove Pointer",
        message: `Remove pointer "${pointer}" from ${activeDomain}?`,
        confirmLabel: "Remove Pointer"
    });
    if (!confirmed) return;
    try {
        await apiRequest(`/api/domains/${activeDomain}/pointers/${pointer}`, "DELETE");
        showAlert("success", "Pointer deleted.");
        invalidateApiCache(`/api/domains/${activeDomain}/pointers`);
        invalidateDomainCache(activeDomain);
        await loadPointersList(activeDomain, { force: true });
        await loadDomainDetails(activeDomain, { force: true });
    } catch (err) {
        showAlert("error", err.message);
    }
}

// 5.5 Catch-All Settings
async function loadCatchAll(domain, { force = false } = {}) {
    const typeSelect = document.getElementById("catch-all-type");
    const addressGroup = document.getElementById("catch-all-address-group");
    const addressInput = document.getElementById("catch-all-address");
    const card = typeSelect?.closest(".glass-card");

    const renderCatchAll = (result) => {
        if (result?.success && result.data) {
            typeSelect.value = result.data.type;
            if (result.data.type === "address") {
                addressGroup.style.display = "block";
                addressInput.value = result.data.address || "";
            } else {
                addressGroup.style.display = "none";
                addressInput.value = "";
            }
        }
    };

    try {
        const url = `/api/domains/${domain}/catch-all`;
        const result = await cachedFetch(url, {
            force,
            onRefreshStart: () => setElementRefreshing(card, true),
            onRefreshEnd: () => setElementRefreshing(card, false),
            onUpdated: renderCatchAll,
        });
        renderCatchAll(result);
    } catch (err) {
        console.warn("Could not load catch-all configuration:", err);
    }
}

// Catch-All Type Visibility Toggle
document.getElementById("catch-all-type").addEventListener("change", (e) => {
    const group = document.getElementById("catch-all-address-group");
    if (e.target.value === "address") {
        group.style.display = "block";
    } else {
        group.style.display = "none";
    }
});

// Catch-All Update Submit
document.getElementById("form-catch-all").addEventListener("submit", async (e) => {
    e.preventDefault();
    const type = document.getElementById("catch-all-type").value;
    const address = document.getElementById("catch-all-address").value.trim();
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/catch-all`, "PATCH", { type, address: type === "address" ? address : null });
        invalidateApiCache(`/api/domains/${activeDomain}/catch-all`);
        showAlert("success", "Catch-All configuration updated.");
    } catch (err) {
        showAlert("error", err.message);
    }
});

function renderDnsHealth(health) {
    const summaryEl = document.getElementById("dns-health-summary");
    const checksEl = document.getElementById("dns-health-checks");
    if (!health) return;

    if (summaryEl) {
        const summaryMap = {
            healthy: "All required DNS records look good in public DNS.",
            degraded: "Mail may work, but some recommended records need attention.",
            unhealthy: "Critical DNS records are missing or incorrect."
        };
        summaryEl.textContent = summaryMap[health.overall] || summaryMap.degraded;
    }

    if (checksEl) {
        setTrustedHtml(checksEl, "");
        Object.values(health.checks || {}).forEach(check => {
            const item = document.createElement("div");
            item.className = `dns-health-item ${check.status}`;
            const statusIcon = window.Mxm?.icons?.dnsStatusIcon(check.status) ?? "";
            item.innerHTML = `
                <div class="dns-health-item-title">${statusIcon} ${escapeHtml(check.label)}</div>
                <div class="dns-health-item-message">${escapeHtml(check.message)}</div>
            `;
            checksEl.appendChild(item);
        });
        checksEl.dataset.loaded = "true";
    }
}

async function loadDnsHealth(domain, { force = false } = {}) {
    if (!domain) return;

    const card = document.getElementById("dns-health-card");
    const checksEl = document.getElementById("dns-health-checks");
    const firstLoad = !hasLoadedContent(checksEl);
    const url = `/api/domains/${domain}/dns/health`;

    const onRefresh = (refreshing) => {
        setElementRefreshing(card, refreshing);
    };

    if (firstLoad && checksEl) {
        setTrustedHtml(checksEl, '<div style="text-align: center; padding: 0.75rem 0; color: var(--color-muted);">Checking DNS records...</div>');
    }

    try {
        const result = await cachedFetch(url, {
            force,
            onRefreshStart: () => onRefresh(true),
            onRefreshEnd: () => onRefresh(false),
            onUpdated: (updated) => {
                if (updated?.success && updated.data) renderDnsHealth(updated.data);
            },
        });

        if (!result.success || !result.data) {
            throw new Error(result.error?.message || "Health check failed");
        }
        renderDnsHealth(result.data);
    } catch (err) {
        if (firstLoad || force) {
            const summaryEl = document.getElementById("dns-health-summary");
            if (summaryEl) summaryEl.textContent = `DNS health check failed: ${err.message}`;
            if (checksEl && firstLoad) setTrustedHtml(checksEl, "");
        }
    }
}

// 5.7 Email Accounts Management
