// 5.8 Forwarders Management
function renderForwardersList(result, domain) {
    const tbody = document.getElementById("forwarders-list-tbody");
    setTrustedHtml(tbody, "");

    if (result?.success && result.data?.length > 0) {
        result.data.forEach(forwarder => {
            const tr = document.createElement("tr");
            tr.dataset.alias = forwarder.alias;
            const destHtml = forwarder.destinations.map(d => `<div style="font-size:0.85rem; color:var(--color-secondary);">${escapeHtml(d)}</div>`).join("");

            tr.innerHTML = `
                <td><strong>${escapeHtml(forwarder.alias)}@${escapeHtml(domain)}</strong></td>
                <td>${destHtml}</td>
                <td style="text-align: right;">
                    ${actionMenuHtml([{ action: "delete", label: "Remove", icon: "trash", danger: true, dataset: { alias: forwarder.alias } }])}
                </td>
            `;
            tbody.appendChild(tr);
        });
    } else {
        setTrustedHtml(tbody, tablePlaceholderRowHtml(3, "No forwarders active for this domain."));
    }
    tbody.dataset.loaded = "true";
}

async function loadForwardersList(domain, { force = false } = {}) {
    const tbody = document.getElementById("forwarders-list-tbody");
    const card = tbody?.closest(".glass-card");
    const firstLoad = !tbody.querySelector("tr[data-alias]") && tbody.dataset.loaded !== "true";

    await fetchCachedList({
        url: `/api/domains/${domain}/forwarders`,
        tbody, card, force, firstLoad,
        render: (result) => renderForwardersList(result, domain),
        loadingHtml: tablePlaceholderRowHtml(3, "Loading forwarders..."),
        errorHtml: (err) => tablePlaceholderRowHtml(3, `Failed to load forwarders: ${err.message}`, { error: true }),
    });
}

document.getElementById("form-create-forwarder").addEventListener("submit", async (e) => {
    e.preventDefault();
    const aliasInput = document.getElementById("forwarder-alias");
    const destsInput = document.getElementById("forwarder-destinations");
    
    const alias = aliasInput.value.trim().toLowerCase();
    const destinations = destsInput.value.split(',').map(d => d.trim()).filter(d => d);
    
    if (!alias || destinations.length === 0) return;
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/forwarders`, "POST", { alias, destinations });
        showAlert("success", `Forwarder for ${alias}@${activeDomain} created!`);
        aliasInput.value = "";
        destsInput.value = "";
        await loadForwardersList(activeDomain, { force: true });
    } catch (err) {
        showAlert("error", err.message);
    }
});

async function handleDeleteForwarder(alias) {
    const forwarderAddress = `${alias}@${activeDomain}`;
    const confirmed = await showTypedConfirm({
        title: "Delete Forwarder",
        message: `Remove the forwarder for ${forwarderAddress}?`,
        expectedValue: forwarderAddress,
        confirmLabel: "Delete Forwarder",
        inputLabel: "Type the forwarder email address to confirm"
    });
    if (!confirmed) return;
    try {
        await apiRequest(`/api/domains/${activeDomain}/forwarders/${alias}`, "DELETE");
        showAlert("success", `Forwarder ${alias}@${activeDomain} deleted.`);
        await loadForwardersList(activeDomain, { force: true });
    } catch (err) {
        showAlert("error", err.message);
    }
}

// 5.9 Spam Control Panel
async function loadSpamSettings(domain, { force = false } = {}) {
    const scoreSlider = document.getElementById("spam-high-score");
    const scoreLbl = document.getElementById("spam-high-score-val");
    const card = scoreSlider?.closest(".glass-card");

    const renderSettings = (result) => {
        if (result?.success && result.data) {
            const score = result.data.high_score;
            scoreSlider.value = score;
            scoreLbl.textContent = score;
        }
    };

    try {
        const url = `/api/domains/${domain}/spam/settings`;
        const result = await cachedFetch(url, {
            force,
            onRefreshStart: () => setElementRefreshing(card, true),
            onRefreshEnd: () => setElementRefreshing(card, false),
            onUpdated: renderSettings,
        });
        renderSettings(result);
    } catch (err) {
        console.warn("Could not load spam settings:", err);
    }

    await Promise.all([
        loadSpamList(domain, "whitelist", { force }),
        loadSpamList(domain, "blacklist", { force }),
    ]);
}

// Spam Score Slider Updater
document.getElementById("spam-high-score").addEventListener("input", (e) => {
    document.getElementById("spam-high-score-val").textContent = e.target.value;
});

// Spam Settings Update Submit
document.getElementById("form-spam-settings").addEventListener("submit", async (e) => {
    e.preventDefault();
    const highScore = parseInt(document.getElementById("spam-high-score").value);
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/spam/settings`, "PATCH", { high_score: highScore });
        invalidateApiCache(`/api/domains/${activeDomain}/spam/settings`);
        showAlert("success", "Spam score threshold updated.");
    } catch (err) {
        showAlert("error", err.message);
    }
});

// Spam whitelist/blacklist loader (type is "whitelist" or "blacklist")
async function loadSpamList(domain, type, { force = false } = {}) {
    const tbody = document.getElementById(`${type}-tbody`);
    const card = tbody?.closest(".glass-card");
    const firstLoad = !tbody.dataset.loaded;

    const render = (result) => {
        setTrustedHtml(tbody, "");
        if (result?.success && result.data?.length > 0) {
            result.data.forEach(entry => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td><strong>${escapeHtml(entry)}</strong></td>
                    <td style="text-align: right;">
                        ${actionMenuHtml([{ action: "remove", label: "Remove", icon: "trash", danger: true, dataset: { entry } }])}
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            setTrustedHtml(tbody, tablePlaceholderRowHtml(2, `No ${type} entries`));
        }
        tbody.dataset.loaded = "true";
    };

    await fetchCachedList({
        url: `/api/domains/${domain}/spam/${type}`,
        tbody, card, force, firstLoad, render,
        loadingHtml: tablePlaceholderRowHtml(2, `Loading ${type}...`),
        errorHtml: (err) => tablePlaceholderRowHtml(2, `Error loading ${type}`, { error: true }),
    });
}

// Add whitelist/blacklist entry submit
["whitelist", "blacklist"].forEach(type => {
    document.getElementById(`form-${type}-add`).addEventListener("submit", async (e) => {
        e.preventDefault();
        const entryInput = document.getElementById(`${type}-entry`);
        const entry = entryInput.value.trim();
        if (!entry) return;

        try {
            await apiRequest(`/api/domains/${activeDomain}/spam/${type}`, "POST", { entry });
            showAlert("success", `Added "${entry}" to ${type}.`);
            entryInput.value = "";
            await loadSpamList(activeDomain, type, { force: true });
        } catch (err) {
            showAlert("error", err.message);
        }
    });
});

async function handleRemoveSpamList(type, entry) {
    const confirmed = await showConfirm({
        title: `Remove from ${type}`,
        message: `Remove "${entry}" from the spam ${type}?`,
        confirmLabel: "Remove"
    });
    if (!confirmed) return;
    try {
        // Encode entry for URL safeness (since it may contain symbols/wildcards)
        const encodedEntry = encodeURIComponent(entry);
        await apiRequest(`/api/domains/${activeDomain}/spam/${type}/${encodedEntry}`, "DELETE");
        showAlert("success", `Removed "${entry}" from ${type}.`);
        await loadSpamList(activeDomain, type, { force: true });
    } catch (err) {
        showAlert("error", err.message);
    }
}

async function initDomainDropdowns() {
    const select = document.getElementById("global-domain-select");
    
    try {
        const result = await cachedFetch("/api/domains");
        setTrustedHtml(select, "");
        
        if (result.success && result.data && result.data.length > 0) {
            result.data.forEach(domain => {
                const option = document.createElement("option");
                option.value = domain;
                option.textContent = domain;
                select.appendChild(option);
            });
            
            // Set first domain as active if not already set, or preserve current if still exists
            if (!activeDomain || !result.data.includes(activeDomain)) {
                activeDomain = result.data[0];
            }
            select.value = activeDomain;
            
            // Load initial page data without blocking the portal domain dropdown.
            await Promise.all([
                triggerDataRefresh(),
                populateResetPortalDomainSelect(),
            ]);
        } else {
            const option = document.createElement("option");
            option.value = "";
            if (currentUser && !currentUser.is_admin) {
                option.textContent = "No domains delegated to you";
                select.appendChild(option);
                activeDomain = "";
                showAlert("warning", "No domains have been delegated to your account. Please contact an administrator.");
            } else {
                option.textContent = "No domains found (Go to Domains Tab)";
                select.appendChild(option);
                activeDomain = "";
                showAlert("warning", "No domains found. Please configure a domain first in the Domains tab.");
            }
        }
    } catch (err) {
        setTrustedHtml(select, '<option value="">Error loading domains</option>');
        showAlert("error", "Failed to retrieve account domains list from server.");
    }
}

// Dropdown Change Handler
document.getElementById("global-domain-select").addEventListener("change", async (e) => {
    activeDomain = e.target.value;
    applyDashboardSectionVisibility();
    // The dashboard refresh below loads DNS health itself; only pre-load it here
    // (to keep the header status current) when another tab is active.
    const activeTab = document.querySelector(".nav-item.active")?.getAttribute("data-tab");
    if (activeTab !== "dashboard" && userHasPermission("dashboard", activeDomain)) {
        await loadDnsHealth(activeDomain);
    }
    if (!activeTabAllowedForDomain()) {
        showAlert("warning", "You do not have access to this section for the selected domain.");
        activateFirstAllowedTab();
        return;
    }
    await triggerDataRefresh();
});
