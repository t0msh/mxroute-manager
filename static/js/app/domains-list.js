async function triggerDataRefresh(options = {}) {
    const { force = false } = options;
    const activeNav = document.querySelector(".nav-item.active");
    if (!activeNav) return;
    const activeTab = activeNav.getAttribute("data-tab");
    if (!activeDomain && activeTab !== "delegations" && activeTab !== "domains" && activeTab !== "settings" && activeTab !== "logs" && activeTab !== "notifications") return;
    
    try {
        switch (activeTab) {
            case "dashboard": {
                const tasks = [];
                if (userHasPermission("dashboard", activeDomain)) {
                    if (!currentUser || currentUser.is_admin) {
                        tasks.push(loadAccountQuota({ force }));
                    }
                    tasks.push(loadDomainDetails(activeDomain, { force }));
                    tasks.push(loadDnsHealth(activeDomain, { force }));
                }
                applyDashboardSectionVisibility();
                await Promise.all(tasks);
                break;
            }
            case "domains":
                applyDomainsSectionVisibility();
                await loadDomainsList({ force });
                break;
            case "emails":
                // Set domain display labels
                document.getElementById("create-email-domain-display").textContent = `@${activeDomain}`;
                await Promise.all([
                    loadEmailsList(activeDomain, { force }),
                    checkDomainMailHostingStatus(activeDomain, { force })
                ]);
                break;
            case "forwarders":
                document.getElementById("forwarder-domain-display").textContent = `@${activeDomain}`;
                await Promise.all([
                    loadForwardersList(activeDomain, { force }),
                    loadCatchAll(activeDomain, { force }),
                    loadPointersList(activeDomain, { force }),
                    checkDomainMailHostingStatus(activeDomain, { force })
                ]);
                break;
            case "spam":
                await Promise.all([
                    loadSpamSettings(activeDomain, { force }),
                    checkDomainMailHostingStatus(activeDomain, { force })
                ]);
                break;
            case "delegations":
                await loadDelegationsPage({ force });
                break;
            case "logs":
                await loadLogsPage();
                break;
            case "notifications":
                await loadNotificationsPage();
                break;
            case "settings":
                await loadSettingsPage();
                break;
        }
    } catch (err) {
        showAlert("error", err.message);
    }
}

// Global Refresh Actions
document.getElementById("btn-refresh-data").addEventListener("click", async () => {
    const refreshBtn = document.getElementById("btn-refresh-data");
    setTrustedHtml(refreshBtn, btnLabel("arrow-clockwise", "Refreshing...", true));
    refreshBtn.disabled = true;
    try {
        await triggerDataRefresh({ force: true });
        showAlert("success", "Data refreshed successfully.");
    } catch (e) {
        showAlert("error", "Refresh failed: " + e.message);
    } finally {
        setTrustedHtml(refreshBtn, btnLabel("arrow-clockwise", "Refresh Data"));
        refreshBtn.disabled = false;
    }
});

// 5.1 Storage Quotas
async function loadAccountQuota({ force = false } = {}) {
    if (currentUser && !currentUser.is_admin) return;
    const card = document.getElementById("dash-quota-card");
    const firstLoad = !hasLoadedContent(document.getElementById("quota-used"));

    const renderQuota = (result) => {
        if (!result?.success || !result.data) return;
        const data = result.data;
        accountQuota = data;
        const limitGB = data.total_limit === 0 ? "Unlimited" : (data.total_limit / (1024 ** 3)).toFixed(1) + " GB";
        const usedGB = (data.total_used / (1024 ** 3)).toFixed(2) + " GB";
        const percent = data.percent_used.toFixed(1) + "%";

        document.getElementById("sidebar-quota-text").textContent = `${usedGB} / ${limitGB}`;
        const bar = document.getElementById("sidebar-quota-bar");
        bar.style.width = percent;
        bar.className = "quota-bar-fill";
        if (data.percent_used > 80) bar.classList.add("warning");
        if (data.percent_used > 95) bar.classList.add("danger");

        document.getElementById("quota-used").textContent = usedGB;
        document.getElementById("quota-limit").textContent = limitGB;
        document.getElementById("quota-percentage").textContent = percent;
        document.getElementById("quota-used").dataset.loaded = "true";

        if (data.grace_period) {
            setTrustedHtml(document.getElementById("quota-grace"), `<span style="color: var(--danger);">Quota Exceeded! Deadline: ${escapeHtml(data.grace_period.deadline)}</span>`);
        } else {
            document.getElementById("quota-grace").textContent = "Compliant";
        }
    };

    try {
        const result = await cachedFetch("/api/quota", {
            force,
            onRefreshStart: () => {
                setElementRefreshing(card, true);
                setSidebarQuotaRefreshing(true);
            },
            onRefreshEnd: () => {
                setElementRefreshing(card, false);
                setSidebarQuotaRefreshing(false);
            },
            onUpdated: renderQuota,
        });
        if (firstLoad && !result?.success) {
            document.getElementById("quota-used").textContent = "--";
        }
        renderQuota(result);
    } catch (err) {
        console.warn("Could not load account quotas:", err);
    }
}

// 5.2 Domains List
function renderDnsStatusBadge(health) {
    return window.Mxm.utils.renderDnsStatusBadge(health);
}

function dnsNeedsFix(health) {
    return window.Mxm.utils.dnsNeedsFix(health);
}

function actionMenuHtml(items) {
    const menuItems = items.map(({ action, label, icon, danger = false, dataset = {}, disabled = false, title = "" }) => {
        const dataAttrs = Object.entries(dataset)
            .map(([key, value]) => `data-${escapeHtml(key)}="${escapeHtml(String(value ?? ""))}"`)
            .join(" ");
        const disabledAttr = disabled ? " disabled" : "";
        const titleAttr = title ? ` title="${escapeHtml(title)}"` : "";
        return `<button type="button" class="action-menu-item${danger ? " action-menu-item-danger" : ""}" role="menuitem" data-action="${escapeHtml(action)}" ${dataAttrs}${disabledAttr}${titleAttr}>${bi(icon)} ${escapeHtml(label)}</button>`;
    }).join("");
    return `
        <div class="action-menu" data-action-menu>
            <button type="button" class="btn btn-secondary btn-sm action-menu-toggle" aria-haspopup="menu" aria-expanded="false">
                ${bi("three-dots-vertical")} Actions
            </button>
            <div class="action-menu-panel" role="menu" hidden>
                ${menuItems}
            </div>
        </div>
    `;
}

function closeActionMenus() {
    document.querySelectorAll("[data-action-menu].is-open").forEach(menu => {
        menu.classList.remove("is-open");
        const toggle = menu.querySelector(".action-menu-toggle");
        const panel = menu.querySelector(".action-menu-panel");
        if (toggle) toggle.setAttribute("aria-expanded", "false");
        if (panel) panel.hidden = true;
    });
}

function ensureActionMenuDocListeners() {
    if (document.body.dataset.actionMenuDocInit) return;
    document.body.dataset.actionMenuDocInit = "true";
    document.addEventListener("click", closeActionMenus);
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeActionMenus();
    });
}

function initTableActionMenus(tbodyId, onItemAction) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody || tbody.dataset.actionMenuInit === "true") return;
    tbody.dataset.actionMenuInit = "true";
    ensureActionMenuDocListeners();

    tbody.addEventListener("click", (event) => {
        const toggle = event.target.closest(".action-menu-toggle");
        if (toggle) {
            event.stopPropagation();
            const menu = toggle.closest("[data-action-menu]");
            const wasOpen = menu?.classList.contains("is-open");
            closeActionMenus();
            if (menu && !wasOpen) {
                menu.classList.add("is-open");
                toggle.setAttribute("aria-expanded", "true");
                const panel = menu.querySelector(".action-menu-panel");
                if (panel) panel.hidden = false;
            }
            return;
        }

        const item = event.target.closest(".action-menu-item");
        if (!item || item.disabled) return;

        event.preventDefault();
        event.stopPropagation();
        closeActionMenus();
        onItemAction(item);
    });
}

function prefetchDomainsListStatus(domains) {
    if (!domains?.length) return;
    // ponytail: defer so interactive requests (reset portal, dropdowns) get browser connection slots first
    window.setTimeout(() => {
        void window.Mxm.utils.mapWithConcurrency(
            domains,
            3,
            (domain) => refreshDomainRowDetails(domain)
        ).catch(() => {});
    }, 400);
}

function domainActionsMenuHtml(domain, options) {
    const {
        fixDnsVisible,
        mailOn,
        webmailReady,
        cfConfigured,
        isAdmin,
        canDns,
    } = options;
    const items = [];
    if (canDns && fixDnsVisible) {
        items.push(`<button type="button" class="action-menu-item" role="menuitem" data-action="fix-dns">${bi("wrench")} Fix DNS entries</button>`);
    }
    if (webmailReady) {
        items.push(`<button type="button" class="action-menu-item" role="menuitem" data-action="webmail-open">${bi("box-arrow-up-right")} Open webmail</button>`);
    } else if (canDns && cfConfigured) {
        items.push(`<button type="button" class="action-menu-item" role="menuitem" data-action="webmail-deploy">${bi("envelope-open")} Set up webmail</button>`);
    }
    if (isAdmin) {
        const routingLabel = mailOn ? "Disable Routing" : "Enable Routing";
        const routingIcon = mailOn ? "toggle-on" : "toggle-off";
        items.push(`<button type="button" class="action-menu-item" role="menuitem" data-action="toggle-routing">${bi(routingIcon)} ${routingLabel}</button>`);
        items.push(`<button type="button" class="action-menu-item action-menu-item-danger" role="menuitem" data-action="delete">${bi("trash")} Delete</button>`);
    }
    if (!items.length) {
        return `<span style="color: var(--color-muted); font-size: 0.85rem;">—</span>`;
    }
    return `
        <div class="action-menu" data-action-menu data-domain="${escapeHtml(domain)}">
            <button type="button" class="btn btn-secondary btn-sm action-menu-toggle" aria-haspopup="menu" aria-expanded="false">
                ${bi("three-dots-vertical")} Actions
            </button>
            <div class="action-menu-panel" role="menu" hidden>
                ${items.join("\n")}
            </div>
        </div>
    `;
}

function renderDomainActionsCell(domain) {
    const safeId = domain.replace(/[^a-zA-Z0-9-]/g, "-");
    const cell = document.getElementById(`domain-actions-${safeId}`);
    if (!cell) return;
    const cached = domainRowCache.get(domain) || {};
    const isAdmin = !!currentUser?.is_admin;
    setTrustedHtml(cell, domainActionsMenuHtml(domain, {
        fixDnsVisible: cached.fixDnsVisible ?? false,
        mailOn: cached.mailOn ?? true,
        webmailReady: cached.webmailReady ?? false,
        cfConfigured: cached.cfConfigured ?? false,
        isAdmin,
        canDns: isAdmin || userHasPermission("dns", domain),
    }));
}

function applyDomainRowDetails(domain, detailsResult, healthResult) {
    const safeId = domain.replace(/[^a-zA-Z0-9-]/g, "-");
    const mailCell = document.getElementById(`domain-mail-${safeId}`);
    const dnsCell = document.getElementById(`domain-dns-${safeId}`);
    if (!mailCell || !dnsCell) return;

    const prev = domainRowCache.get(domain) || {};
    let mailHtml = `<span style="color: var(--color-muted); font-size: 0.85rem;">Unknown</span>`;
    let dnsHtml = `<span style="color: var(--color-muted); font-size: 0.85rem;">Unknown</span>`;
    let fixDnsVisible = prev.fixDnsVisible ?? false;
    let mailOn = prev.mailOn ?? null;
    let webmailReady = prev.webmailReady ?? false;
    let cfConfigured = prev.cfConfigured ?? false;

    if (detailsResult?.success && detailsResult.data) {
        mailOn = !!detailsResult.data.mail_hosting;
        mailHtml = mailOn
            ? `<span class="status-indicator success"><span class="dot"></span> Enabled</span>`
            : `<span class="status-indicator danger"><span class="dot"></span> Disabled</span>`;
    }

    if (healthResult?.success && healthResult.data) {
        const health = healthResult.data;
        dnsHtml = renderDnsStatusBadge(health);
        fixDnsVisible = dnsNeedsFix(health);
        webmailReady = health.checks?.webmail?.status === "pass";
        cfConfigured = !!health.cf_configured;
    }

    setTrustedHtml(mailCell, mailHtml);
    setTrustedHtml(dnsCell, dnsHtml);

    domainRowCache.set(domain, { mailHtml, dnsHtml, fixDnsVisible, mailOn, webmailReady, cfConfigured });
    renderDomainActionsCell(domain);
}

