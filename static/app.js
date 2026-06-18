// --- 1. Global App State & Helpers ---
let activeDomain = "";
let activeDomainMailHosting = null;
let accountQuota = null;
let currentUser = null;
let oidcEnabled = false;
let knownDelegationUsers = new Set();
let lastCreatedMailboxCredentials = null;
let delegationPermissionCatalog = [...window.Mxm.permissions.DELEGATION_PERMISSION_CATALOG];

const DELEGATION_PERMISSION_LABELS = {
    dashboard: "Dashboard",
    emails: "Email Accounts",
    forwarders: "Forwarders",
    spam: "Spam Controls",
    dns: "DNS Records",
};

function bi(name, extraClass = "") {
    return window.Mxm?.icons?.icon(name, extraClass) ?? "";
}

function btnLabel(iconName, text, loading = false) {
    const spin = loading ? " bi-spin" : "";
    return `${bi(iconName, spin)} ${text}`;
}

function userHasPermission(permission, domain = activeDomain) {
    return window.Mxm.permissions.userHasPermission(currentUser, permission, domain);
}

function userHasAnyPermission(permissions, domain = activeDomain) {
    return window.Mxm.permissions.userHasAnyPermission(currentUser, permissions, domain);
}

function getUserPermissionUnion() {
    return window.Mxm.permissions.getUserPermissionUnion(currentUser, delegationPermissionCatalog);
}

function tabVisibleForUser(tab) {
    return window.Mxm.permissions.tabVisibleForUser(currentUser, tab, delegationPermissionCatalog);
}

function activeTabAllowedForDomain() {
    const activeTab = document.querySelector(".nav-item.active")?.getAttribute("data-tab");
    if (!activeTab || !activeDomain) return true;
    if (activeTab === "dashboard") {
        return userHasAnyPermission(["dashboard", "dns"], activeDomain);
    }
    const required = window.Mxm.permissions.TAB_REQUIRED_PERMISSION[activeTab];
    return !required || userHasPermission(required, activeDomain);
}

function applyDashboardSectionVisibility() {
    const statsGrid = document.querySelector("#tab-dashboard .stats-grid");
    const quotaCard = document.getElementById("dash-quota-card");
    const dnsHealthCard = document.getElementById("dns-health-card");
    const mailToggle = document.getElementById("btn-toggle-mail-hosting");
    const hasDashboard = userHasPermission("dashboard", activeDomain);

    if (statsGrid) statsGrid.style.display = hasDashboard ? "" : "none";
    if (quotaCard) quotaCard.style.display = currentUser?.is_admin && hasDashboard ? "" : "none";
    if (dnsHealthCard) dnsHealthCard.style.display = hasDashboard ? "" : "none";
    if (mailToggle) mailToggle.style.display = currentUser?.is_admin ? "" : "none";
}

function applyDomainsSectionVisibility() {
    const isAdmin = !!currentUser?.is_admin;
    const newModeOption = document.querySelector('input[name="setup-domain-mode"][value="new"]')?.closest(".setup-mode-option");
    if (newModeOption) newModeOption.style.display = isAdmin ? "" : "none";
    const step3 = document.querySelector(".setup-wizard-step[data-step=\"3\"]");
    if (step3) step3.style.display = isAdmin ? "" : "none";
}

function applyUserPermissionsUI() {
    if (!currentUser) return;

    const navTabs = {
        dashboard: document.querySelector('.nav-item[data-tab="dashboard"]'),
        domains: document.getElementById("nav-tab-domains"),
        emails: document.querySelector('.nav-item[data-tab="emails"]'),
        forwarders: document.querySelector('.nav-item[data-tab="forwarders"]'),
        spam: document.querySelector('.nav-item[data-tab="spam"]'),
        delegations: document.getElementById("nav-tab-delegations"),
        logs: document.getElementById("nav-tab-logs"),
        settings: document.getElementById("nav-tab-settings"),
    };

    if (currentUser.is_admin) {
        Object.values(navTabs).forEach(tab => {
            if (tab) tab.style.display = tab.id === "nav-tab-delegations" || tab.id === "nav-tab-logs" ? "flex" : "";
        });
        document.getElementById("sidebar-quota-container").style.display = "";
        document.getElementById("dash-quota-card").style.display = "";
        applyDashboardSectionVisibility();
        return;
    }

    document.getElementById("nav-tab-delegations").style.display = "none";
    document.getElementById("nav-tab-logs").style.display = "none";
    document.getElementById("sidebar-quota-container").style.display = "none";
    document.getElementById("dash-quota-card").style.display = "none";

    Object.entries(navTabs).forEach(([tab, el]) => {
        if (!el || tab === "delegations" || tab === "logs") return;
        el.style.display = tabVisibleForUser(tab) ? "" : "none";
    });

    applyDashboardSectionVisibility();
    applyDomainsSectionVisibility();
    activateFirstAllowedTab();
}

function activateFirstAllowedTab() {
    const activeTab = document.querySelector(".nav-item.active")?.getAttribute("data-tab");
    if (activeTab && tabVisibleForUser(activeTab) && activeTabAllowedForDomain()) return;

    const fallbackOrder = ["dashboard", "domains", "emails", "forwarders", "spam", "settings"];
    const nextTab = fallbackOrder.find(tab => tabVisibleForUser(tab));
    if (!nextTab) return;

    const navItem = document.querySelector(`.nav-item[data-tab="${nextTab}"]`);
    if (navItem) navItem.click();
}

function escapeHtml(value) {
    return window.Mxm.utils.escapeHtml(value);
}

function jsAttrString(value) {
    return window.Mxm.utils.jsAttrString(value);
}

function secureRandomInt(max) {
    const buffer = new Uint32Array(1);
    crypto.getRandomValues(buffer);
    return buffer[0] % max;
}

function shuffleString(str) {
    const chars = str.split("");
    for (let i = chars.length - 1; i > 0; i--) {
        const j = secureRandomInt(i + 1);
        [chars[i], chars[j]] = [chars[j], chars[i]];
    }
    return chars.join("");
}

// Parse fetch body as JSON; surface HTML/empty gateway responses clearly.
async function parseJsonResponse(response) {
    const text = await response.text();
    if (!text) {
        throw new Error(`Empty response from server (HTTP ${response.status}).`);
    }
    try {
        return JSON.parse(text);
    } catch {
        const preview = text.replace(/\s+/g, " ").trim().slice(0, 120);
        throw new Error(
            response.ok
                ? "Server returned a non-JSON response."
                : `Server error (HTTP ${response.status}): ${preview || "no body"}`
        );
    }
}

function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return "";
}

// Helper to make API requests easily
async function apiRequest(url, method = "GET", body = null) {
    const options = {
        method,
        headers: {
            "Content-Type": "application/json"
        }
    };
    if (body) {
        options.body = JSON.stringify(body);
    }

    if (method !== "GET") {
        const csrfToken = getCookie("csrf_token");
        if (csrfToken) {
            options.headers["X-CSRF-Token"] = csrfToken;
        }
    }
    
    try {
        const response = await fetch(url, options);
        let result;
        try {
            result = await response.json();
        } catch (e) {
            result = { success: response.ok };
        }
        
        if (!response.ok) {
            const errMsg = result.error ? result.error.message : `HTTP Error ${response.status}`;
            throw new Error(errMsg);
        }
        return result;
    } catch (err) {
        console.error(`API Request failed on ${url}:`, err);
        throw err;
    }
}

// --- Data cache (stale-while-revalidate) ---
const apiCache = new Map();
const domainRowCache = new Map();
const backgroundRefreshes = new Map();

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

// Shared skeleton for table loaders: loading placeholder -> cachedFetch (with
// refresh indicator + background revalidation) -> render -> error row. Each caller
// supplies its own firstLoad heuristic, render fn, and placeholder/error markup.
async function fetchCachedList({ url, tbody, card, force, firstLoad, render, loadingHtml, errorHtml }) {
    if (firstLoad) tbody.innerHTML = loadingHtml;
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
            tbody.innerHTML = typeof errorHtml === "function" ? errorHtml(err) : errorHtml;
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

function hasLoadedContent(el) {
    if (!el) return false;
    if (el.dataset.loaded === "true") return true;
    if (el.id === "domains-list-tbody") return !!el.querySelector("tr[data-domain]");
    if (el.id === "dns-health-checks") return el.children.length > 0;
    return el.textContent.trim() !== "" && el.textContent.trim() !== "--";
}

// Show Toast Alerts
let alertDismissTimer = null;
function showAlert(type, message) {
    const banner = document.getElementById("alert-banner");
    const icon = document.getElementById("alert-banner-icon");
    const text = document.getElementById("alert-banner-text");
    
    banner.className = `alert-banner ${type}`;
    const alertIcons = window.Mxm?.icons?.ALERT_ICONS ?? {};
    icon.innerHTML = bi(alertIcons[type] || "bell");
    text.textContent = message;
    
    banner.classList.add("show");
    
    if (alertDismissTimer) {
        clearTimeout(alertDismissTimer);
        alertDismissTimer = null;
    }
    if (type === "success" || type === "info") {
        alertDismissTimer = setTimeout(dismissAlert, 5000);
    }
}

function dismissAlert() {
    if (alertDismissTimer) {
        clearTimeout(alertDismissTimer);
        alertDismissTimer = null;
    }
    document.getElementById("alert-banner").classList.remove("show");
}

let _confirmResolver = null;
let _typedConfirmResolver = null;

function initConfirmModals() {
    const confirmModal = document.getElementById("modal-confirm");
    const typedModal = document.getElementById("modal-typed-confirm");
    const typedInput = document.getElementById("modal-typed-confirm-input");
    const typedSubmit = document.getElementById("modal-typed-confirm-submit");

    function closeConfirm(result) {
        confirmModal.classList.remove("show");
        if (_confirmResolver) {
            _confirmResolver(result);
            _confirmResolver = null;
        }
    }

    function closeTypedConfirm(result) {
        typedModal.classList.remove("show");
        typedInput.value = "";
        typedInput.classList.remove("matching");
        typedSubmit.disabled = true;
        if (_typedConfirmResolver) {
            _typedConfirmResolver(result);
            _typedConfirmResolver = null;
        }
    }

    document.getElementById("modal-confirm-submit").addEventListener("click", () => closeConfirm(true));
    document.getElementById("modal-confirm-cancel").addEventListener("click", () => closeConfirm(false));
    document.getElementById("modal-confirm-close").addEventListener("click", () => closeConfirm(false));

    document.getElementById("modal-typed-confirm-submit").addEventListener("click", () => {
        if (!typedSubmit.disabled) closeTypedConfirm(true);
    });
    document.getElementById("modal-typed-confirm-cancel").addEventListener("click", () => closeTypedConfirm(false));
    document.getElementById("modal-typed-confirm-close").addEventListener("click", () => closeTypedConfirm(false));

    typedInput.addEventListener("input", () => {
        const expected = typedInput.dataset.expected || "";
        const matches = typedInput.value.trim().toLowerCase() === expected.toLowerCase();
        typedSubmit.disabled = !matches;
        typedInput.classList.toggle("matching", matches);
    });

    typedInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !typedSubmit.disabled) {
            event.preventDefault();
            closeTypedConfirm(true);
        }
    });
}

function showConfirm({ title, message, confirmLabel = "Confirm", variant = "danger" }) {
    return new Promise((resolve) => {
        _confirmResolver = resolve;
        document.getElementById("modal-confirm-title").textContent = title;
        document.getElementById("modal-confirm-message").textContent = message;
        const submitBtn = document.getElementById("modal-confirm-submit");
        submitBtn.textContent = confirmLabel;
        submitBtn.className = variant === "danger" ? "btn btn-danger btn-sm" : "btn btn-primary btn-sm";
        document.getElementById("modal-confirm").classList.add("show");
    });
}

function showTypedConfirm({ title, message, expectedValue, confirmLabel = "Delete", inputLabel = "Type the email address to confirm" }) {
    return new Promise((resolve) => {
        _typedConfirmResolver = resolve;
        const input = document.getElementById("modal-typed-confirm-input");
        document.getElementById("modal-typed-confirm-title").textContent = title;
        document.getElementById("modal-typed-confirm-message").textContent = message;
        document.getElementById("modal-typed-confirm-label").textContent = inputLabel;
        document.getElementById("modal-typed-confirm-hint").textContent = `Enter exactly: ${expectedValue}`;
        document.getElementById("modal-typed-confirm-submit").textContent = confirmLabel;
        input.value = "";
        input.dataset.expected = expectedValue;
        input.classList.remove("matching");
        document.getElementById("modal-typed-confirm-submit").disabled = true;
        document.getElementById("modal-typed-confirm").classList.add("show");
        setTimeout(() => input.focus(), 100);
    });
}

// Copy to Clipboard Utility
async function copyText(elementId) {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    try {
        await navigator.clipboard.writeText(element.textContent || element.innerText);
        showAlert("success", "Copied to clipboard!");
    } catch (err) {
        showAlert("error", "Failed to copy text.");
    }
}

async function copyMailboxCredentials() {
    const creds = lastCreatedMailboxCredentials;
    if (!creds?.email || !creds?.password) {
        showAlert("warning", "No credentials to copy.");
        return;
    }

    try {
        await navigator.clipboard.writeText(formatMailboxCredentialsText(creds));
        showAlert("success", "Mailbox credentials copied to clipboard!");
    } catch (err) {
        showAlert("error", "Failed to copy credentials.");
    }
}

function formatMailboxCredentialsText(creds) {
    return window.Mxm.utils.formatMailboxCredentialsText(creds);
}

function showMailboxCredentials(creds) {
    lastCreatedMailboxCredentials = creds;
    document.getElementById("out-email-addr").textContent = creds.email;
    document.getElementById("out-email-pass").textContent = creds.password;
    document.getElementById("out-imap-host").textContent = creds.imapHost;
    document.getElementById("out-smtp-host").textContent = creds.smtpHost;
    document.getElementById("out-webmail-url").textContent = creds.webmailUrl;
    document.getElementById("credentials-output-card").style.display = "block";
    document.getElementById("credentials-output-card").scrollIntoView({ behavior: "smooth" });
}

// Modal Toggle Helpers
function openModal(modalId) {
    document.getElementById(modalId).classList.add("show");
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove("show");
}

// Password Generator
function generateRandomPassword() {
    const length = 16;
    const charset = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+~`|}{[]:;?><,./-=";
    let retVal = "";
    
    retVal += "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[secureRandomInt(26)];
    retVal += "abcdefghijklmnopqrstuvwxyz"[secureRandomInt(26)];
    retVal += "0123456789"[secureRandomInt(10)];
    retVal += "!@#$%^&*()_+~`|}{[]:;?><,./-="[secureRandomInt(29)];
    
    for (let i = 4; i < length; ++i) {
        retVal += charset[secureRandomInt(charset.length)];
    }
    
    return shuffleString(retVal);
}

// --- 2. Live Password Verification Logic ---
const requirements = {
    length: /.{8,}/,
    upper: /[A-Z]/,
    lower: /[a-z]/,
    number: /[0-9]/,
    special: /[^A-Za-z0-9]/
};

function setupPasswordValidation(inputId, listId, buttonId) {
    const input = document.getElementById(inputId);
    const list = document.getElementById(listId);
    const button = document.getElementById(buttonId);
    if (!input || !list || !button) return;

    input.addEventListener("input", () => {
        const val = input.value;
        let allValid = true;

        for (const [key, regex] of Object.entries(requirements)) {
            const el = list.querySelector(`[data-req="${key}"]`);
            if (el) {
                if (regex.test(val)) {
                    el.classList.add("valid");
                    window.Mxm?.icons?.setReqIcon(el, true);
                } else {
                    el.classList.remove("valid");
                    window.Mxm?.icons?.setReqIcon(el, false);
                    allValid = false;
                }
            }
        }
        button.disabled = !allValid;
    });
}

// Initialize Password Validations
setupPasswordValidation("create-email-password", "create-email-requirements", "btn-provision-submit");
setupPasswordValidation("modal-pass-input", "modal-pass-requirements", "btn-modal-pass-submit");


// --- 3. Tab Navigation Controller ---
document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", () => {
        // Toggle Nav States
        document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
        item.classList.add("active");
        
        // Toggle Panel States
        const tab = item.getAttribute("data-tab");
        document.querySelectorAll(".tab-panel").forEach(panel => panel.classList.remove("active"));
        document.getElementById(`tab-${tab}`).classList.add("active");
        
        // Show/hide global domain selector (not needed on Domains, Access Control, or Settings pages)
        const domainSelector = document.getElementById("global-domain-selector");
        if (tab === "domains" || tab === "delegations" || tab === "settings" || tab === "logs") {
            domainSelector.style.display = "none";
        } else {
            domainSelector.style.display = "";
        }
        
        // Update Title & Page details
        const titleMap = {
            dashboard: { title: "Dashboard", subtitle: "Overview of your hosted mail accounts, resources, and endpoints." },
            domains: { title: "Domain Management", subtitle: "Register domains, verify DNS records, and configure redirection." },
            emails: { title: "Email Mailboxes", subtitle: "Provision new accounts, change quotas, and modify routing parameters." },
            forwarders: { title: "Email Forwarders", subtitle: "Create forwarders to redirect messages to external addresses." },
            spam: { title: "Spam & Whitelist Controls", subtitle: "Configure SpamAssassin thresholds and manage list records." },
            delegations: { title: "Access Control", subtitle: "Delegate email domain management rights to specific users." },
            logs: { title: "System Logs", subtitle: "View system actions, administrator operations, and authentication audits." },
            settings: { title: "Settings", subtitle: "Configure global system parameters, authentication methods, and user interface options." }
        };
        
        const titleInfo = titleMap[tab];
        if (titleInfo) {
            document.getElementById("page-title").textContent = titleInfo.title;
            document.getElementById("page-subtitle").textContent = titleInfo.subtitle;
        }
        
        // Reload page specific data (uses cache when still fresh)
        if (!activeTabAllowedForDomain()) {
            showAlert("warning", "You do not have access to this section for the selected domain.");
            activateFirstAllowedTab();
            return;
        }
        triggerDataRefresh();
    });
});


// --- 4. Main Data Refresher ---
async function triggerDataRefresh(options = {}) {
    const { force = false } = options;
    const activeNav = document.querySelector(".nav-item.active");
    if (!activeNav) return;
    const activeTab = activeNav.getAttribute("data-tab");
    if (!activeDomain && activeTab !== "delegations" && activeTab !== "domains" && activeTab !== "settings" && activeTab !== "logs") return;
    
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
    refreshBtn.innerHTML = btnLabel("arrow-clockwise", "Refreshing...", true);
    refreshBtn.disabled = true;
    try {
        await triggerDataRefresh({ force: true });
        showAlert("success", "Data refreshed successfully.");
    } catch (e) {
        showAlert("error", "Refresh failed: " + e.message);
    } finally {
        refreshBtn.innerHTML = btnLabel("arrow-clockwise", "Refresh Data");
        refreshBtn.disabled = false;
    }
});


// --- 5. Specific Feature Functions ---

// 5.1 Storage Quotas
async function loadAccountQuota({ force = false } = {}) {
    if (currentUser && !currentUser.is_admin) return;
    const card = document.getElementById("dash-quota-card");
    const sidebar = document.getElementById("sidebar-quota-container");
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
            document.getElementById("quota-grace").innerHTML = `<span style="color: var(--danger);">Quota Exceeded! Deadline: ${escapeHtml(data.grace_period.deadline)}</span>`;
        } else {
            document.getElementById("quota-grace").textContent = "Compliant";
        }
    };

    try {
        const result = await cachedFetch("/api/quota", {
            force,
            onRefreshStart: () => {
                setElementRefreshing(card, true);
                setElementRefreshing(sidebar, true);
            },
            onRefreshEnd: () => {
                setElementRefreshing(card, false);
                setElementRefreshing(sidebar, false);
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

function applyDomainRowDetails(domain, detailsResult, healthResult) {
    const safeId = domain.replace(/[^a-zA-Z0-9-]/g, "-");
    const mailCell = document.getElementById(`domain-mail-${safeId}`);
    const dnsCell = document.getElementById(`domain-dns-${safeId}`);
    const fixDnsBtn = document.getElementById(`domain-fix-dns-${safeId}`);
    if (!mailCell || !dnsCell) return;

    let mailHtml = `<span style="color: var(--color-muted); font-size: 0.85rem;">Unknown</span>`;
    let dnsHtml = `<span style="color: var(--color-muted); font-size: 0.85rem;">Unknown</span>`;
    let fixDnsVisible = true;

    if (detailsResult?.success && detailsResult.data) {
        const mailOn = detailsResult.data.mail_hosting;
        mailHtml = mailOn
            ? `<span class="status-indicator success"><span class="dot"></span> Enabled</span>`
            : `<span class="status-indicator danger"><span class="dot"></span> Disabled</span>`;
    }

    if (healthResult?.success && healthResult.data) {
        const health = healthResult.data;
        dnsHtml = renderDnsStatusBadge(health);
        fixDnsVisible = dnsNeedsFix(health);
    }

    mailCell.innerHTML = mailHtml;
    dnsCell.innerHTML = dnsHtml;
    if (fixDnsBtn) fixDnsBtn.style.display = fixDnsVisible ? "inline-flex" : "none";

    domainRowCache.set(domain, { mailHtml, dnsHtml, fixDnsVisible });
}

async function refreshDomainRowDetails(domain, { force = false } = {}) {
    const safeId = domain.replace(/[^a-zA-Z0-9-]/g, "-");
    const mailCell = document.getElementById(`domain-mail-${safeId}`);
    const dnsCell = document.getElementById(`domain-dns-${safeId}`);
    if (!mailCell || !dnsCell) return;

    const detailsUrl = `/api/domains/${domain}`;
    const healthUrl = `/api/domains/${domain}/dns/setup-health`;
    const rowCached = domainRowCache.get(domain);

    if (rowCached) {
        mailCell.innerHTML = rowCached.mailHtml;
        dnsCell.innerHTML = rowCached.dnsHtml;
        const fixDnsBtn = document.getElementById(`domain-fix-dns-${safeId}`);
        if (fixDnsBtn) fixDnsBtn.style.display = rowCached.fixDnsVisible ? "inline-flex" : "none";
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
    tbody.innerHTML = "";
    domains.forEach(domain => {
        const safeId = domain.replace(/[^a-zA-Z0-9-]/g, "-");
        const cached = domainRowCache.get(domain);
        const tr = document.createElement("tr");
        tr.dataset.domain = domain;
        tr.innerHTML = `
            <td><strong>${escapeHtml(domain)}</strong></td>
            <td id="domain-mail-${safeId}">${cached?.mailHtml || `<span style="color: var(--color-muted); font-size: 0.85rem;">—</span>`}</td>
            <td id="domain-dns-${safeId}">${cached?.dnsHtml || `<span style="color: var(--color-muted); font-size: 0.85rem;">—</span>`}</td>
            <td style="text-align: right;">
                <button class="btn btn-secondary btn-sm" id="domain-fix-dns-${safeId}" style="display: ${cached?.fixDnsVisible ? "inline-flex" : "none"};" onclick="openDomainDnsSetup(${jsAttrString(domain)})">Fix DNS</button>
                ${currentUser?.is_admin ? `<button class="btn btn-danger btn-sm" onclick="handleDeleteDomain(${jsAttrString(domain)})">Delete</button>` : ""}
            </td>
        `;
        tbody.appendChild(tr);
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
        btn.innerHTML = btnLabel("arrow-clockwise", "Refreshing...", true);
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
            btn.innerHTML = btnLabel("arrow-clockwise", "Refresh status");
        }
    }
}

async function loadDomainsList({ force = false } = {}) {
    const tbody = document.getElementById("domains-list-tbody");
    const card = document.getElementById("domains-list-card");
    const hasRows = !!tbody.querySelector("tr[data-domain]");
    const firstLoad = !hasRows;

    if (firstLoad) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--color-muted);">Querying domains...</td></tr>';
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
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--color-muted);">No domains found on this account.</td></tr>';
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
    } catch (err) {
        if (firstLoad || !hasRows) {
            tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--danger); font-weight: 500;">Failed to load domains: ${escapeHtml(err.message)}</td></tr>`;
        } else {
            showAlert("error", `Failed to refresh domains: ${err.message}`);
        }
    }
}

// 5.3 Domain Details (Dashboard Overview)
async function loadDomainDetails(domain, { force = false } = {}) {
    if (!domain) return;
    const statsGrid = document.querySelector("#tab-dashboard .stats-grid");
    const firstLoad = !hasLoadedContent(document.getElementById("dash-mailboxes-count"));

    const renderDetails = (result, mailboxRes) => {
        if (result?.success && result.data) {
            const data = result.data;
            activeDomainMailHosting = !!data.mail_hosting;
            document.getElementById("dash-mail-status").innerHTML = data.mail_hosting
                ? `<span class="status-indicator success"><span class="dot"></span> Enabled</span>`
                : `<span class="status-indicator danger"><span class="dot"></span> Disabled</span>`;
            document.getElementById("dash-pointers-count").textContent = data.pointers ? data.pointers.length : 0;
            document.getElementById("dash-mailboxes-count").dataset.loaded = "true";
        }

        if (mailboxRes?.success && mailboxRes.data) {
            document.getElementById("dash-mailboxes-count").textContent = mailboxRes.data.length;
        } else if (mailboxRes) {
            document.getElementById("dash-mailboxes-count").textContent = 0;
        }
    };

    try {
        const detailsUrl = `/api/domains/${domain}`;
        const mailboxesUrl = `/api/domains/${domain}/email-accounts`;

        const result = await cachedFetch(detailsUrl, {
            force,
            onRefreshStart: () => setElementRefreshing(statsGrid, true),
            onRefreshEnd: () => setElementRefreshing(statsGrid, false),
            onUpdated: async (updated) => {
                const mailboxRes = apiCache.get(mailboxesUrl)?.data
                    || await cachedFetch(mailboxesUrl, { force: true });
                renderDetails(updated, mailboxRes);
            },
        });

        let mailboxRes = apiCache.get(mailboxesUrl)?.data;
        const mailboxesFresh = isCacheFresh(mailboxesUrl);
        if (!mailboxRes || force || !mailboxesFresh) {
            mailboxRes = await cachedFetch(mailboxesUrl, {
                force,
                onRefreshStart: () => setElementRefreshing(statsGrid, true),
                onRefreshEnd: () => setElementRefreshing(statsGrid, false),
            });
        }
        renderDetails(result, mailboxRes);
    } catch (err) {
        console.warn("Could not load domain details:", err);
        if (firstLoad) {
            document.getElementById("dash-mailboxes-count").textContent = "--";
        }
    }
}

// Toggle Mail Hosting status
document.getElementById("btn-toggle-mail-hosting").addEventListener("click", async () => {
    if (!activeDomain || activeDomainMailHosting === null) return;
    const nextState = !activeDomainMailHosting;
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/mail-status`, "PATCH", { enabled: nextState });
        showAlert("success", `Mail hosting status updated successfully.`);
        invalidateDomainCache(activeDomain);
        await loadDomainDetails(activeDomain, { force: true });
    } catch (err) {
        showAlert("error", err.message);
    }
});

// --- Domain & DNS Setup Wizard ---
let setupWizardDomain = "";
let setupWizardStep = 1;
let setupCfConfigured = false;
let setupCurrentHealth = null;

function getSetupDomainValue() {
    const mode = document.querySelector('input[name="setup-domain-mode"]:checked')?.value;
    if (mode === "new") {
        return document.getElementById("setup-domain-input")?.value.trim().toLowerCase() || "";
    }
    return document.getElementById("setup-domain-select")?.value || "";
}

function setSetupWizardStep(step) {
    setupWizardStep = step;
    document.querySelectorAll(".setup-wizard-step").forEach(el => {
        el.classList.toggle("active", parseInt(el.dataset.step, 10) === step);
        el.classList.toggle("completed", parseInt(el.dataset.step, 10) < step);
    });
    document.getElementById("setup-step-1").style.display = step === 1 ? "block" : "none";
    document.getElementById("setup-step-2").style.display = step === 2 ? "block" : "none";
    document.getElementById("setup-step-3").style.display = step === 3 ? "block" : "none";
}

async function populateSetupDomainSelect() {
    const select = document.getElementById("setup-domain-select");
    if (!select) return;
    select.innerHTML = '<option value="">Loading domains...</option>';
    try {
        const result = await apiRequest("/api/domains");
        select.innerHTML = "";
        if (result.success && result.data && result.data.length > 0) {
            result.data.forEach(domain => {
                const option = document.createElement("option");
                option.value = domain;
                option.textContent = domain;
                select.appendChild(option);
            });
        } else {
            select.innerHTML = '<option value="">No domains on MXroute yet</option>';
        }
    } catch {
        select.innerHTML = '<option value="">Error loading domains</option>';
    }
}

// --- Password Reset Portal ---
let resetPortalDomain = "";
let resetPortalLoadedPrefix = "";
let resetPortalSelectedTheme = "emerald";

function highlightResetPortalTheme(themeId) {
    const theme = themeId || "emerald";
    resetPortalSelectedTheme = theme;
    document.querySelectorAll("#reset-portal-theme-grid .portal-theme-card").forEach(card => {
        card.classList.toggle("active", card.getAttribute("data-portal-theme") === theme);
    });
}

function linkifyMessageUrl(message, url) {
    const msg = message || "";
    if (!url || !msg.includes(url)) return escapeHtml(msg);
    const idx = msg.indexOf(url);
    return `${escapeHtml(msg.slice(0, idx))}<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url)}</a>${escapeHtml(msg.slice(idx + url.length))}`;
}

async function populateResetPortalDomainSelect() {
    const select = document.getElementById("reset-portal-domain-select");
    if (!select) return;
    select.innerHTML = '<option value="">Loading domains...</option>';
    try {
        const result = await cachedFetch("/api/domains");
        select.innerHTML = '<option value="">Select a domain...</option>';
        if (result.success && result.data?.length) {
            result.data.forEach(domain => {
                const option = document.createElement("option");
                option.value = domain;
                option.textContent = domain;
                select.appendChild(option);
            });
            if (resetPortalDomain) {
                select.value = resetPortalDomain;
            }
        } else {
            select.innerHTML = '<option value="">No domains on MXroute yet</option>';
        }
    } catch {
        select.innerHTML = '<option value="">Error loading domains</option>';
    }
}

function updateResetPortalUrlPreview() {
    const preview = document.getElementById("reset-portal-url-preview");
    const prefixInput = document.getElementById("reset-portal-prefix");
    if (!preview || !prefixInput) return;
    const prefix = prefixInput.value.trim().toLowerCase() || "reset";
    const domain = resetPortalDomain || "example.com";
    preview.textContent = `https://${prefix}.${domain}`;
}

function renderResetPortalForm(data) {
    const form = document.getElementById("reset-portal-form");
    if (!form) return;
    form.style.display = resetPortalDomain ? "block" : "none";
    if (!data) return;

    document.getElementById("reset-portal-enabled").checked = !!data.enabled;
    document.getElementById("reset-portal-prefix").value = data.subdomain_prefix || "";
    document.getElementById("reset-portal-title").value = data.portal_title || "";
    highlightResetPortalTheme(data.portal_theme || "emerald");
    resetPortalLoadedPrefix = data.subdomain_prefix || "";

    const logoPreview = document.getElementById("reset-portal-logo-preview");
    const deleteLogoBtn = document.getElementById("btn-reset-portal-logo-delete");
    if (data.has_logo && resetPortalDomain) {
        logoPreview.src = `/api/domains/${encodeURIComponent(resetPortalDomain)}/reset-portal/logo-preview?t=${Date.now()}`;
        logoPreview.style.display = "block";
        if (deleteLogoBtn) deleteLogoBtn.style.display = "inline-flex";
    } else {
        logoPreview.removeAttribute("src");
        logoPreview.style.display = "none";
        if (deleteLogoBtn) deleteLogoBtn.style.display = "none";
    }

    const dnsStatus = document.getElementById("reset-portal-dns-status");
    const httpsStatus = document.getElementById("reset-portal-https-status");
    const deployMissing = document.getElementById("reset-portal-deploy-missing");
    const deployBtn = document.getElementById("btn-reset-portal-deploy-dns");

    if (deployMissing) {
        const missing = data.deploy_missing || [];
        deployMissing.style.display = missing.length ? "block" : "none";
        const list = document.getElementById("reset-portal-deploy-missing-list");
        if (list) list.textContent = missing.join(", ");
    }
    if (deployBtn) {
        deployBtn.style.display = data.deploy_configured ? "inline-flex" : "none";
        deployBtn.disabled = !data.enabled || !data.subdomain_prefix;
    }

    if (dnsStatus && data.dns) {
        dnsStatus.style.display = "block";
        const status = data.dns.status;
        dnsStatus.className = `status-banner mb-4 ${status === "pass" ? "success" : status === "fail" ? "error" : status === "pending" ? "warning" : "info"}`;
        dnsStatus.textContent = data.dns.message || "";
    } else if (dnsStatus) {
        dnsStatus.style.display = "none";
    }

    if (httpsStatus && data.https) {
        httpsStatus.style.display = "block";
        const status = data.https.status;
        httpsStatus.className = `status-banner mb-4 ${status === "pass" ? "success" : status === "fail" ? "error" : status === "pending" ? "warning" : "info"}`;
        const httpsUrl = data.https.url || (status === "pass" ? data.portal_url : "");
        httpsStatus.innerHTML = linkifyMessageUrl(data.https.message || "", httpsUrl);
    } else if (httpsStatus) {
        httpsStatus.style.display = "none";
    }

    updateResetPortalUrlPreview();
}

async function loadResetPortalSettings(domain) {
    resetPortalDomain = (domain || "").toLowerCase().trim();
    if (!resetPortalDomain) {
        renderResetPortalForm(null);
        return;
    }
    try {
        const result = await apiRequest(`/api/domains/${resetPortalDomain}/reset-portal`);
        renderResetPortalForm(result.data);
    } catch (err) {
        showAlert("error", err.message);
    }
}

function initResetPortal() {
    const select = document.getElementById("reset-portal-domain-select");
    if (!select) return;

    populateResetPortalDomainSelect();

    select.addEventListener("change", () => {
        loadResetPortalSettings(select.value);
    });

    document.getElementById("reset-portal-prefix")?.addEventListener("input", () => {
        updateResetPortalUrlPreview();
        const warning = document.getElementById("reset-portal-prefix-warning");
        const prefix = document.getElementById("reset-portal-prefix")?.value.trim().toLowerCase() || "";
        if (warning) {
            warning.style.display = resetPortalLoadedPrefix && prefix && prefix !== resetPortalLoadedPrefix
                ? "block"
                : "none";
        }
    });

    document.querySelectorAll("#reset-portal-theme-grid .portal-theme-card").forEach(card => {
        card.addEventListener("click", () => {
            highlightResetPortalTheme(card.getAttribute("data-portal-theme"));
        });
    });

    document.getElementById("btn-reset-portal-save")?.addEventListener("click", async () => {
        if (!resetPortalDomain) {
            showAlert("warning", "Select a domain first.");
            return;
        }
        const enabled = document.getElementById("reset-portal-enabled").checked;
        const subdomain_prefix = document.getElementById("reset-portal-prefix").value.trim().toLowerCase();
        const portal_title = document.getElementById("reset-portal-title").value.trim();
        const portal_theme = resetPortalSelectedTheme;
        if (enabled && !subdomain_prefix) {
            showAlert("warning", "Subdomain prefix is required when the portal is enabled.");
            return;
        }
        try {
            const result = await apiRequest(
                `/api/domains/${resetPortalDomain}/reset-portal`,
                "PATCH",
                { enabled, subdomain_prefix, portal_title, portal_theme }
            );
            showAlert("success", "Reset portal settings saved.");
            if (result.data?.teardown_steps?.length) {
                showAlert("info", result.data.teardown_steps.join(" · "));
            }
            renderResetPortalForm(result.data);
        } catch (err) {
            showAlert("error", err.message);
        }
    });

    document.getElementById("reset-portal-logo")?.addEventListener("change", async (event) => {
        if (!resetPortalDomain) return;
        const file = event.target.files?.[0];
        if (!file) return;
        const formData = new FormData();
        formData.append("logo", file);
        try {
            const response = await fetch(`/api/domains/${encodeURIComponent(resetPortalDomain)}/reset-portal/logo`, {
                method: "POST",
                headers: { "X-CSRF-Token": getCookie("csrf_token") || "" },
                body: formData,
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error?.message || "Logo upload failed.");
            }
            showAlert("success", "Logo uploaded.");
            renderResetPortalForm(result.data);
        } catch (err) {
            showAlert("error", err.message);
        } finally {
            event.target.value = "";
        }
    });

    document.getElementById("btn-reset-portal-logo-delete")?.addEventListener("click", async () => {
        if (!resetPortalDomain) return;
        try {
            const result = await apiRequest(
                `/api/domains/${resetPortalDomain}/reset-portal/logo`,
                "DELETE"
            );
            showAlert("success", "Logo removed.");
            renderResetPortalForm(result.data);
        } catch (err) {
            showAlert("error", err.message);
        }
    });

    document.getElementById("btn-reset-portal-deploy-dns")?.addEventListener("click", async () => {
        if (!resetPortalDomain) return;
        const btn = document.getElementById("btn-reset-portal-deploy-dns");
        if (btn) {
            btn.disabled = true;
            btn.textContent = "Deploying...";
        }
        try {
            const controller = new AbortController();
            const deployTimeout = window.setTimeout(() => controller.abort(), 180000);
            const response = await fetch(
                `/api/domains/${encodeURIComponent(resetPortalDomain)}/reset-portal/deploy-dns`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRF-Token": getCookie("csrf_token") || "",
                    },
                    body: JSON.stringify({}),
                    signal: controller.signal,
                }
            );
            window.clearTimeout(deployTimeout);
            const result = await parseJsonResponse(response);
            if (!response.ok || !result.success) {
                throw new Error(result.error?.message || "Deploy failed.");
            }
            const https = result.data?.https;
            if (https?.status === "pass") {
                showAlert("success", "Reset portal deployed and HTTPS is live.");
            } else {
                showAlert(
                    "success",
                    "DNS and NPM configured. HTTPS may take a few minutes — refresh this page to recheck."
                );
            }
            await loadResetPortalSettings(resetPortalDomain);
        } catch (err) {
            const message = err.name === "AbortError"
                ? "Deploy timed out after 3 minutes. Check NPM and try again."
                : err.message;
            showAlert("error", message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = "Deploy Portal (DNS + NPM)";
            }
        }
    });
}

function renderSetupDnsChecks(health) {
    const checksEl = document.getElementById("setup-dns-checks");
    const fixAllBtn = document.getElementById("btn-setup-fix-all-dns");
    if (!checksEl) return;

    checksEl.innerHTML = "";
    setupCurrentHealth = health;

    const fixable = [];
    Object.entries(health.checks || {}).forEach(([key, check]) => {
        const item = document.createElement("div");
        const statusClass = check.status === "pass" ? "pass" : check.status === "pending" ? "pending" : check.status === "skipped" ? "skipped" : check.status;
        const statusIcon = window.Mxm?.icons?.dnsStatusIcon(check.status) ?? "";
        const canFix = setupCfConfigured && (check.status === "warn" || check.status === "fail");
        if (canFix) fixable.push(key);

        item.className = `dns-health-item ${statusClass}`;
        item.innerHTML = `
            <div class="dns-health-item-title">${statusIcon} ${escapeHtml(check.label)}</div>
            <div class="dns-health-item-message">${escapeHtml(check.message)}</div>
            ${canFix ? `<button class="btn btn-secondary btn-sm setup-fix-btn" data-record="${escapeHtml(key)}" style="margin-top: 0.6rem;">Fix in Cloudflare</button>` : ""}
        `;
        checksEl.appendChild(item);
    });

    checksEl.querySelectorAll(".setup-fix-btn").forEach(btn => {
        btn.addEventListener("click", () => handleFixDnsRecord(btn.dataset.record));
    });

    if (fixAllBtn) {
        fixAllBtn.style.display = fixable.length > 0 ? "inline-flex" : "none";
    }

    const pendingNotice = document.getElementById("setup-mxroute-pending-notice");
    const completeNotice = document.getElementById("setup-mxroute-complete-notice");
    const step2MxrouteBtn = document.getElementById("btn-setup-step2-mxroute");
    const step2DoneBtn = document.getElementById("btn-setup-step2-done");

    if (pendingNotice) pendingNotice.style.display = health.on_mxroute ? "none" : "block";
    if (completeNotice) completeNotice.style.display = health.on_mxroute ? "block" : "none";

    const hasPendingMail = Object.values(health.checks || {}).some(c => c.status === "pending");
    const hasIssues = Object.values(health.checks || {}).some(c => c.status === "warn" || c.status === "fail");

    if (step2MxrouteBtn) {
        step2MxrouteBtn.style.display = !health.on_mxroute && currentUser?.is_admin ? "inline-flex" : "none";
    }
    if (step2DoneBtn) {
        step2DoneBtn.style.display = health.on_mxroute && !hasIssues && !hasPendingMail ? "inline-flex" : "none";
    }
}

async function loadSetupDnsHealth() {
    if (!setupWizardDomain) return;
    const label = document.getElementById("setup-domain-label");
    if (label) {
        label.innerHTML = `<strong>Domain:</strong> ${escapeHtml(setupWizardDomain)}`;
    }

    const checksEl = document.getElementById("setup-dns-checks");
    if (checksEl) {
        checksEl.innerHTML = '<div style="color: var(--color-muted); padding: 1rem;">Running DNS health check...</div>';
    }

    try {
        const result = await apiRequest(`/api/domains/${setupWizardDomain}/dns/setup-health`);
        if (!result.success || !result.data) {
            throw new Error(result.error?.message || "Health check failed");
        }
        if (result.data?.cf_configured !== undefined) {
            setupCfConfigured = !!result.data.cf_configured;
            const cfMissing = document.getElementById("setup-cf-missing");
            if (cfMissing) cfMissing.style.display = setupCfConfigured ? "none" : "block";
        }
        renderSetupDnsChecks(result.data);
    } catch (err) {
        if (checksEl) {
            checksEl.innerHTML = `<div class="dns-health-item fail"><div class="dns-health-item-message">${escapeHtml(err.message)}</div></div>`;
        }
        showAlert("error", err.message);
    }
}

function showSetupDnsProgress(steps, isError = false) {
    const container = document.getElementById("setup-dns-progress");
    const list = document.getElementById("setup-dns-progress-list");
    if (!container || !list) return;
    container.style.display = "block";
    list.innerHTML = "";
    (steps || []).forEach(step => {
        list.innerHTML += `<li>${bi("check-circle-fill")} ${escapeHtml(step)}</li>`;
    });
    if (isError) {
        list.innerHTML += `<li style="color: var(--danger);">${bi("x-circle-fill")} See alert for details</li>`;
    }
}

async function handleFixDnsRecord(recordType) {
    if (!setupWizardDomain) return;
    try {
        const result = await apiRequest(
            `/api/domains/${setupWizardDomain}/dns/fix`,
            "POST",
            { records: [recordType] }
        );
        if (result.data?.steps) showSetupDnsProgress(result.data.steps);
        const fixed = result.data?.fixed || [];
        if (fixed.length > 0) {
            showAlert("success", `Updated ${fixed.join(", ").toUpperCase()} in Cloudflare. DNS propagation may take a few minutes.`);
        } else {
            showAlert("info", "Record already exists or was not applicable.");
        }
        await loadSetupDnsHealth();
        invalidateDomainCache(setupWizardDomain);
        await loadDomainsList({ force: true });
    } catch (err) {
        if (err.steps) showSetupDnsProgress(err.steps, true);
        showAlert("error", err.message);
    }
}

async function handleFixAllDns() {
    if (!setupWizardDomain) return;
    const btn = document.getElementById("btn-setup-fix-all-dns");
    if (btn) btn.disabled = true;
    try {
        const result = await apiRequest(
            `/api/domains/${setupWizardDomain}/dns/fix`,
            "POST",
            {}
        );
        if (result.data?.steps) showSetupDnsProgress(result.data.steps);
        const fixed = result.data?.fixed || [];
        if (fixed.length > 0) {
            showAlert("success", `Fixed: ${fixed.join(", ").toUpperCase()}. DNS propagation may take a few minutes.`);
        } else {
            showAlert("info", "No missing records to fix.");
        }
        await loadSetupDnsHealth();
        invalidateDomainCache(setupWizardDomain);
        await loadDomainsList({ force: true });
    } catch (err) {
        if (err.steps) showSetupDnsProgress(err.steps, true);
        showAlert("error", err.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

function openDomainDnsSetup(domain, startStep = 2) {
    setupWizardDomain = domain.toLowerCase().trim();
    document.querySelector('input[name="setup-domain-mode"][value="existing"]').checked = true;
    document.getElementById("setup-existing-container").style.display = "block";
    document.getElementById("setup-new-container").style.display = "none";

    populateSetupDomainSelect().then(() => {
        const select = document.getElementById("setup-domain-select");
        if (select) select.value = setupWizardDomain;
        setSetupWizardStep(startStep);
        if (startStep >= 2) loadSetupDnsHealth();
        if (startStep === 3) updateSetupStep3State();
        document.getElementById("domain-setup-wizard")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
}

async function updateSetupStep3State() {
    const label = document.getElementById("setup-step3-domain-label");
    const statusEl = document.getElementById("setup-mxroute-status");
    const registerBtn = document.getElementById("btn-setup-register-mxroute");
    const returnBtn = document.getElementById("btn-setup-step3-dns");

    if (label) label.innerHTML = `<strong>Domain:</strong> ${escapeHtml(setupWizardDomain)}`;

    try {
        const result = await apiRequest(`/api/domains/${setupWizardDomain}/dns/setup-health`);
        const onMxroute = result.data?.on_mxroute;
        if (statusEl) {
            statusEl.innerHTML = onMxroute
                ? `<span class="status-indicator success"><span class="dot"></span> Already registered on MXroute</span>`
                : `<span class="status-indicator warning"><span class="dot"></span> Not yet registered on MXroute</span>`;
        }
        if (registerBtn) registerBtn.style.display = onMxroute ? "none" : "inline-flex";
        if (returnBtn) returnBtn.style.display = onMxroute ? "inline-flex" : "none";
    } catch (err) {
        if (statusEl) statusEl.innerHTML = `<span style="color: var(--danger);">${escapeHtml(err.message)}</span>`;
    }
}

function initSetupWizard() {
    document.querySelectorAll('input[name="setup-domain-mode"]').forEach(radio => {
        radio.addEventListener("change", () => {
            const isNew = radio.value === "new" && radio.checked;
            document.getElementById("setup-existing-container").style.display = isNew ? "none" : "block";
            document.getElementById("setup-new-container").style.display = isNew ? "block" : "none";
        });
    });

    document.getElementById("btn-setup-step1-next")?.addEventListener("click", async () => {
        const domain = getSetupDomainValue();
        if (!domain) {
            showAlert("warning", "Please select or enter a domain name.");
            return;
        }
        setupWizardDomain = domain;
        setSetupWizardStep(2);
        await loadSetupDnsHealth();
    });

    document.getElementById("btn-setup-step2-back")?.addEventListener("click", () => setSetupWizardStep(1));
    document.getElementById("btn-setup-step2-mxroute")?.addEventListener("click", async () => {
        setSetupWizardStep(3);
        await updateSetupStep3State();
    });
    document.getElementById("btn-setup-step2-done")?.addEventListener("click", () => {
        showAlert("success", `DNS setup complete for ${setupWizardDomain}.`);
        setSetupWizardStep(1);
    });
    document.getElementById("btn-setup-recheck-dns")?.addEventListener("click", loadSetupDnsHealth);
    document.getElementById("btn-setup-fix-all-dns")?.addEventListener("click", handleFixAllDns);

    document.getElementById("btn-setup-step3-back")?.addEventListener("click", async () => {
        setSetupWizardStep(2);
        await loadSetupDnsHealth();
    });
    document.getElementById("btn-setup-step3-dns")?.addEventListener("click", async () => {
        setSetupWizardStep(2);
        await loadSetupDnsHealth();
    });

    document.getElementById("btn-setup-register-mxroute")?.addEventListener("click", async () => {
        const btn = document.getElementById("btn-setup-register-mxroute");
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = btnLabel("arrow-clockwise", "Registering...", true);
        }
        try {
            await apiRequest("/api/domains", "POST", { domain: setupWizardDomain });
            showAlert("success", `${setupWizardDomain} registered on MXroute. Return to Step 2 to add DKIM and mail DNS records.`);
            invalidateApiCache("/api/domains");
            await initDomainDropdowns();
            await loadDomainsList({ force: true });
            await updateSetupStep3State();
            document.getElementById("btn-setup-step3-dns").style.display = "inline-flex";
        } catch (err) {
            showAlert("error", err.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = "Register Domain on MXroute";
            }
        }
    });

    populateSetupDomainSelect();
}

// Delete Domain
async function handleDeleteDomain(domain) {
    const confirmed = await showTypedConfirm({
        title: "Delete Domain",
        message: `This will permanently delete "${domain}" and destroy all associated mailboxes and configurations.`,
        expectedValue: domain,
        confirmLabel: "Delete Domain",
        inputLabel: "Type the domain name to confirm"
    });
    if (!confirmed) return;
    
    try {
        await apiRequest(`/api/domains/${domain}`, "DELETE");
        showAlert("success", `Domain "${domain}" deleted successfully.`);
        invalidateApiCache("/api/domains");
        invalidateDomainCache(domain);
        await loadDomainsList({ force: true });
        await initDomainDropdowns();
    } catch (err) {
        showAlert("error", err.message);
    }
}

// 5.4 Domain Pointers
async function loadPointersList(domain, { force = false } = {}) {
    const tbody = document.getElementById("pointers-tbody");
    const card = tbody?.closest(".glass-card");
    const firstLoad = !tbody.querySelector("tr[data-pointer]");

    const renderPointers = (result) => {
        tbody.innerHTML = "";
        if (result?.success && result.data?.length > 0) {
            result.data.forEach(pointer => {
                const tr = document.createElement("tr");
                tr.dataset.pointer = pointer.pointer;
                tr.innerHTML = `
                    <td><strong>${escapeHtml(pointer.pointer)}</strong></td>
                    <td><span class="badge" style="font-size:0.75rem; padding:0.1rem 0.4rem; background:rgba(255,255,255,0.05); border: 1px solid var(--glass-border); border-radius:4px;">${escapeHtml(pointer.type)}</span></td>
                    <td style="text-align: right;">
                        <button class="btn btn-danger btn-sm btn-icon" onclick="handleDeletePointer(${jsAttrString(pointer.pointer)})">×</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">No pointers configured</td></tr>';
        }
    };

    await fetchCachedList({
        url: `/api/domains/${domain}/pointers`,
        tbody, card, force, firstLoad, render: renderPointers,
        loadingHtml: '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">Loading pointers...</td></tr>',
        errorHtml: '<tr><td colspan="3" style="text-align: center; color: var(--danger);">Failed to load pointers</td></tr>',
    });
}

// Add Pointer Modal Open
document.getElementById("btn-open-pointer-modal").addEventListener("click", () => {
    document.getElementById("pointer-name-input").value = "";
    openModal("modal-add-pointer");
});

// Create Pointer Form Submit
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

// Delete Pointer
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

function updateDnsHealthHeader(health) {
    const statusEl = document.getElementById("dns-health-status");
    const textEl = document.getElementById("dns-health-status-text");
    if (!statusEl || !textEl) return;

    if (!health) {
        statusEl.className = "status-indicator";
        textEl.textContent = "No domain selected";
        return;
    }

    const labels = {
        healthy: { className: "status-indicator success", text: "DNS Healthy" },
        degraded: { className: "status-indicator warning", text: "DNS Degraded" },
        unhealthy: { className: "status-indicator danger", text: "DNS Issues Detected" }
    };
    const cfg = labels[health.overall] || labels.degraded;
    const mxrouteNote = health.mxroute_reachable === false ? " · MXroute unreachable" : "";
    statusEl.className = cfg.className;
    textEl.textContent = `${cfg.text}${mxrouteNote}`;
}

function renderDnsHealth(health) {
    const summaryEl = document.getElementById("dns-health-summary");
    const checksEl = document.getElementById("dns-health-checks");
    if (!health) return;

    updateDnsHealthHeader(health);

    if (summaryEl) {
        const summaryMap = {
            healthy: "All required DNS records look good in public DNS.",
            degraded: "Mail may work, but some recommended records need attention.",
            unhealthy: "Critical DNS records are missing or incorrect."
        };
        summaryEl.textContent = summaryMap[health.overall] || summaryMap.degraded;
    }

    if (checksEl) {
        checksEl.innerHTML = "";
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
    if (!domain) {
        updateDnsHealthHeader(null);
        return;
    }

    const card = document.getElementById("dns-health-card");
    const headerStatus = document.getElementById("dns-health-status");
    const checksEl = document.getElementById("dns-health-checks");
    const firstLoad = !hasLoadedContent(checksEl);
    const url = `/api/domains/${domain}/dns/health`;

    const onRefresh = (refreshing) => {
        setElementRefreshing(card, refreshing);
        setElementRefreshing(headerStatus, refreshing);
    };

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
            updateDnsHealthHeader({ overall: "unhealthy", mxroute_reachable: false });
            const summaryEl = document.getElementById("dns-health-summary");
            if (summaryEl) summaryEl.textContent = `DNS health check failed: ${err.message}`;
            if (checksEl && firstLoad) checksEl.innerHTML = "";
        }
    }
}

// 5.7 Email Accounts Management
function maskRecoveryEmail(email) {
    if (!email || !email.includes("@")) return "—";
    const [local, domain] = email.split("@");
    if (local.length <= 1) return `*@${domain}`;
    return `${local[0]}${"*".repeat(Math.min(3, local.length - 1))}@${domain}`;
}

function renderEmailsList(result, domain) {
    const tbody = document.getElementById("emails-list-tbody");
    tbody.innerHTML = "";

    if (result?.success && result.data?.length > 0) {
        result.data.forEach(account => {
            const tr = document.createElement("tr");
            tr.dataset.username = account.username;

            const quotaVal = account.quota === 0 ? "Unlimited" : `${account.quota} MB`;
            const quotaPercent = account.quota === 0 ? 0 : Math.min(100, (account.usage / account.quota) * 100);
            const quotaColor = quotaPercent > 90 ? "danger" : (quotaPercent > 75 ? "warning" : "");
            const limitVal = account.limit;
            const sentPercent = Math.min(100, (account.sent / account.limit) * 100);

            const recoveryLabel = account.has_recovery_email
                ? escapeHtml(maskRecoveryEmail(account.recovery_email))
                : '<span style="color: var(--color-muted);">—</span>';

            tr.innerHTML = `
                <td>
                    <div style="font-weight: 600;">${escapeHtml(account.username)}@${escapeHtml(domain)}</div>
                    ${account.suspended ? `<span style="font-size:0.75rem; color: var(--danger); font-weight:500;">${bi("slash-circle")} Suspended</span>` : ''}
                </td>
                <td>
                    <div style="font-size:0.85rem;">${recoveryLabel}</div>
                </td>
                <td>
                    <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:var(--color-secondary); margin-bottom: 0.25rem;">
                        <span>${escapeHtml(account.usage.toFixed(1))} MB used</span>
                        <span>Limit: ${escapeHtml(quotaVal)}</span>
                    </div>
                    <div class="quota-bar" style="height: 4px;">
                        <div class="quota-bar-fill ${quotaColor}" style="width: ${account.quota === 0 ? '1%' : quotaPercent + '%'}"></div>
                    </div>
                </td>
                <td>
                    <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:var(--color-secondary); margin-bottom: 0.25rem;">
                        <span>${escapeHtml(account.sent)} sent today</span>
                        <span>Limit: ${escapeHtml(limitVal)}</span>
                    </div>
                    <div class="quota-bar" style="height: 4px;">
                        <div class="quota-bar-fill" style="width: ${sentPercent}%; background: var(--accent);"></div>
                    </div>
                </td>
                <td style="text-align: right;">
                    <div class="flex-row" style="justify-content: flex-end; gap: 0.5rem;">
                        <button class="btn btn-secondary btn-sm" onclick="openRecoveryModal(${jsAttrString(account.username)}, ${jsAttrString(account.recovery_email || "")})">${bi("envelope")} Recovery</button>
                        <button class="btn btn-secondary btn-sm" onclick="openPasswordModal(${jsAttrString(account.username)})">${bi("key")} Pass</button>
                        <button class="btn btn-secondary btn-sm" onclick="openQuotaModal(${jsAttrString(account.username)}, ${Number(account.quota)}, ${Number(account.limit)})">${bi("gear")} Limit</button>
                        <button class="btn btn-secondary btn-sm" onclick="handleToggleSuspend(${jsAttrString(account.username)}, ${account.suspended ? "true" : "false"})">${account.suspended ? `${bi("check-circle")} Activate` : `${bi("slash-circle")} Suspend`}</button>
                        <button class="btn btn-danger btn-sm" onclick="handleDeleteEmail(${jsAttrString(account.username)})">${bi("trash")} Delete</button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } else {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--color-muted);">No mailboxes found for this domain.</td></tr>';
    }
    tbody.dataset.loaded = "true";
}

async function loadEmailsList(domain, { force = false } = {}) {
    const tbody = document.getElementById("emails-list-tbody");
    const card = tbody?.closest(".glass-card");
    const firstLoad = !tbody.querySelector("tr[data-username]") && tbody.dataset.loaded !== "true";

    await fetchCachedList({
        url: `/api/domains/${domain}/email-accounts`,
        tbody, card, force, firstLoad,
        render: (result) => renderEmailsList(result, domain),
        loadingHtml: '<tr><td colspan="5" style="text-align: center; color: var(--color-muted);">Querying mailboxes...</td></tr>',
        errorHtml: (err) => `<tr><td colspan="5" style="text-align: center; color: var(--danger);">Failed to load email accounts: ${escapeHtml(err.message)}</td></tr>`,
    });
}

// Check if domain has mail hosting enabled and update the UI overlay
async function checkDomainMailHostingStatus(domain, { force = false } = {}) {
    const emailOverlay = document.getElementById("email-hosting-disabled-overlay");
    const forwardersOverlay = document.getElementById("forwarders-hosting-disabled-overlay");
    const spamOverlay = document.getElementById("spam-hosting-disabled-overlay");

    const applyHosting = (result) => {
        if (result?.success && result.data) {
            const displayMode = result.data.mail_hosting ? "none" : "flex";
            if (emailOverlay) emailOverlay.style.display = displayMode;
            if (forwardersOverlay) forwardersOverlay.style.display = displayMode;
            if (spamOverlay) spamOverlay.style.display = displayMode;
        } else {
            if (emailOverlay) emailOverlay.style.display = "none";
            if (forwardersOverlay) forwardersOverlay.style.display = "none";
            if (spamOverlay) spamOverlay.style.display = "none";
        }
    };

    try {
        const url = `/api/domains/${domain}`;
        const result = await cachedFetch(url, { force, onUpdated: applyHosting });
        applyHosting(result);
    } catch (err) {
        console.warn("Could not check domain mail hosting status:", err);
        if (emailOverlay) emailOverlay.style.display = "none";
        if (forwardersOverlay) forwardersOverlay.style.display = "none";
        if (spamOverlay) spamOverlay.style.display = "none";
    }
}

// Generate Password on provisioning form
document.getElementById("btn-generate-password").addEventListener("click", () => {
    const input = document.getElementById("create-email-password");
    input.value = generateRandomPassword();
    input.dispatchEvent(new Event("input")); // Trigger validations
    // Temporarily show password text
    input.type = "text";
    setTimeout(() => { input.type = "password"; }, 5000);
    showAlert("success", "Generated secure password. Visible for 5 seconds.");
});

document.getElementById("btn-copy-mailbox-credentials")?.addEventListener("click", copyMailboxCredentials);

// Create Email Account Submit
document.getElementById("form-create-email").addEventListener("submit", async (e) => {
    e.preventDefault();
    const usernameInput = document.getElementById("create-email-username");
    const passwordInput = document.getElementById("create-email-password");
    const quotaInput = document.getElementById("create-email-quota");
    const limitInput = document.getElementById("create-email-limit");
    const recoveryInput = document.getElementById("create-email-recovery");
    
    const username = usernameInput.value.trim().toLowerCase();
    const password = passwordInput.value;
    const quota = parseInt(quotaInput.value);
    const limit = parseInt(limitInput.value);
    const recoveryEmail = recoveryInput?.value.trim().toLowerCase() || "";
    
    if (!username || !password) return;

    if (recoveryEmail && recoveryEmail === `${username}@${activeDomain}`) {
        showAlert("error", "Recovery email must differ from the mailbox address.");
        return;
    }
    
    const submitBtn = document.getElementById("btn-provision-submit");
    submitBtn.disabled = true;
    submitBtn.innerHTML = btnLabel("arrow-clockwise", "Provisioning...", true);
    
    try {
        const payload = {
            username,
            password,
            quota,
            limit
        };
        if (recoveryEmail) payload.recovery_email = recoveryEmail;

        await apiRequest(`/api/domains/${activeDomain}/email-accounts`, "POST", payload);
        
        // Show Credentials card
        showMailboxCredentials({
            email: `${username}@${activeDomain}`,
            password,
            imapHost: `mail.${activeDomain}`,
            smtpHost: `mail.${activeDomain}`,
            webmailUrl: `https://webmail.${activeDomain}`,
        });
        
        showAlert("success", `Mailbox ${username}@${activeDomain} created successfully!`);
        
        // Reset Form
        usernameInput.value = "";
        passwordInput.value = "";
        if (recoveryInput) recoveryInput.value = "";
        quotaInput.value = 1024;
        document.getElementById("create-email-quota-val").textContent = "1024 MB";
        limitInput.value = 9600;
        document.getElementById("create-email-limit-val").textContent = "9600 / day";
        
        // Reset password rules visualizer
        document.querySelectorAll("#create-email-requirements li").forEach(li => {
            li.classList.remove("valid");
            window.Mxm?.icons?.setReqIcon(li, false);
        });
        
        await loadEmailsList(activeDomain, { force: true });
        await loadAccountQuota({ force: true });
    } catch (err) {
        showAlert("error", err.message);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Provision Mailbox";
    }
});

// Sliders Value Updaters
document.getElementById("create-email-quota").addEventListener("input", (e) => {
    const val = parseInt(e.target.value);
    document.getElementById("create-email-quota-val").textContent = val === 0 ? "Unlimited" : `${val} MB`;
});

document.getElementById("create-email-limit").addEventListener("input", (e) => {
    const val = parseInt(e.target.value);
    document.getElementById("create-email-limit-val").textContent = `${val} / day`;
});

// Delete Email Account
async function handleDeleteEmail(username) {
    const emailAddress = `${username}@${activeDomain}`;
    const confirmed = await showTypedConfirm({
        title: "Delete Mailbox",
        message: `This will permanently delete ${emailAddress} and wipe all stored messages. This cannot be undone.`,
        expectedValue: emailAddress,
        confirmLabel: "Delete Mailbox",
        inputLabel: "Type the email address to confirm"
    });
    if (!confirmed) return;
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/email-accounts/${username}`, "DELETE");
        showAlert("success", `Mailbox ${username}@${activeDomain} deleted.`);
        await loadEmailsList(activeDomain, { force: true });
        await loadAccountQuota({ force: true });
    } catch (err) {
        showAlert("error", err.message);
    }
}

// Toggle Email Account Suspension
async function handleToggleSuspend(username, isSuspended) {
    const suspended = isSuspended === true || isSuspended === "true";
    const actionText = suspended ? "activate" : "suspend";
    const emailAddress = `${username}@${activeDomain}`;
    const confirmed = await showConfirm({
        title: suspended ? "Activate Mailbox" : "Suspend Mailbox",
        message: `Are you sure you want to ${actionText} ${emailAddress}?`,
        confirmLabel: suspended ? "Activate" : "Suspend",
        variant: suspended ? "primary" : "danger"
    });
    if (!confirmed) return;
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/email-accounts/${username}`, "PATCH", { suspended: !suspended });
        showAlert("success", `Mailbox ${username}@${activeDomain} ${actionText}d successfully.`);
        await loadEmailsList(activeDomain, { force: true });
    } catch (err) {
        showAlert("error", err.message);
    }
}

// Password Modal Controllers
function openPasswordModal(username) {
    document.getElementById("modal-pass-username").value = username;
    document.getElementById("modal-pass-email-display").textContent = `${username}@${activeDomain}`;
    document.getElementById("modal-pass-input").value = "";
    
    // Reset password validations
    document.querySelectorAll("#modal-pass-requirements li").forEach(li => {
        li.classList.remove("valid");
        window.Mxm?.icons?.setReqIcon(li, false);
    });
    document.getElementById("btn-modal-pass-submit").disabled = true;
    
    openModal("modal-update-password");
}

document.getElementById("form-modal-update-pass").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("modal-pass-username").value;
    const password = document.getElementById("modal-pass-input").value;
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/email-accounts/${username}`, "PATCH", { password });
        showAlert("success", `Password updated for ${username}@${activeDomain}`);
        closeModal("modal-update-password");
    } catch (err) {
        showAlert("error", err.message);
    }
});

function openRecoveryModal(username, currentRecovery = "") {
    document.getElementById("modal-recovery-username").value = username;
    document.getElementById("modal-recovery-email-display").textContent = `${username}@${activeDomain}`;
    document.getElementById("modal-recovery-input").value = currentRecovery || "";
    openModal("modal-update-recovery");
}

document.getElementById("form-modal-update-recovery").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("modal-recovery-username").value;
    const recoveryEmail = document.getElementById("modal-recovery-input").value.trim().toLowerCase();
    const mailboxEmail = `${username}@${activeDomain}`;

    if (recoveryEmail && recoveryEmail === mailboxEmail) {
        showAlert("error", "Recovery email must differ from the mailbox address.");
        return;
    }

    try {
        const payload = recoveryEmail ? { recovery_email: recoveryEmail } : { recovery_email: null };
        await apiRequest(`/api/domains/${activeDomain}/email-accounts/${username}/recovery`, "PATCH", payload);
        showAlert("success", recoveryEmail
            ? `Recovery email updated for ${mailboxEmail}.`
            : `Recovery email removed for ${mailboxEmail}.`);
        closeModal("modal-update-recovery");
        await loadEmailsList(activeDomain, { force: true });
    } catch (err) {
        showAlert("error", err.message);
    }
});

// Quota & Limit Modal Controllers
function openQuotaModal(username, currentQuota, currentLimit) {
    document.getElementById("modal-quota-username").value = username;
    document.getElementById("modal-quota-email-display").textContent = `${username}@${activeDomain}`;
    
    const quotaSlider = document.getElementById("modal-quota-input");
    const limitSlider = document.getElementById("modal-limit-input");
    
    quotaSlider.value = currentQuota;
    document.getElementById("modal-quota-val-lbl").textContent = currentQuota === 0 ? "Unlimited" : `${currentQuota} MB`;
    
    limitSlider.value = currentLimit;
    document.getElementById("modal-limit-val-lbl").textContent = `${currentLimit} / day`;
    
    openModal("modal-update-quota");
}

document.getElementById("modal-quota-input").addEventListener("input", (e) => {
    const val = parseInt(e.target.value);
    document.getElementById("modal-quota-val-lbl").textContent = val === 0 ? "Unlimited" : `${val} MB`;
});

document.getElementById("modal-limit-input").addEventListener("input", (e) => {
    const val = parseInt(e.target.value);
    document.getElementById("modal-limit-val-lbl").textContent = `${val} / day`;
});

document.getElementById("form-modal-update-quota").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("modal-quota-username").value;
    const quota = parseInt(document.getElementById("modal-quota-input").value);
    const limit = parseInt(document.getElementById("modal-limit-input").value);
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/email-accounts/${username}`, "PATCH", { quota, limit });
        showAlert("success", `Resource parameters updated for ${username}@${activeDomain}`);
        closeModal("modal-update-quota");
        await loadEmailsList(activeDomain, { force: true });
    } catch (err) {
        showAlert("error", err.message);
    }
});


// 5.8 Forwarders Management
function renderForwardersList(result, domain) {
    const tbody = document.getElementById("forwarders-list-tbody");
    tbody.innerHTML = "";

    if (result?.success && result.data?.length > 0) {
        result.data.forEach(forwarder => {
            const tr = document.createElement("tr");
            tr.dataset.alias = forwarder.alias;
            const destHtml = forwarder.destinations.map(d => `<div style="font-size:0.85rem; color:var(--color-secondary);">${escapeHtml(d)}</div>`).join("");

            tr.innerHTML = `
                <td><strong>${escapeHtml(forwarder.alias)}@${escapeHtml(domain)}</strong></td>
                <td>${destHtml}</td>
                <td style="text-align: right;">
                    <button class="btn btn-danger btn-sm" onclick="handleDeleteForwarder(${jsAttrString(forwarder.alias)})">Remove</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } else {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">No forwarders active for this domain.</td></tr>';
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
        loadingHtml: '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">Loading forwarders...</td></tr>',
        errorHtml: (err) => `<tr><td colspan="3" style="text-align: center; color: var(--danger);">Failed to load forwarders: ${escapeHtml(err.message)}</td></tr>`,
    });
}

// Create Forwarder Submit
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

// Delete Forwarder
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
        tbody.innerHTML = "";
        if (result?.success && result.data?.length > 0) {
            result.data.forEach(entry => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td><strong>${escapeHtml(entry)}</strong></td>
                    <td style="text-align: right;">
                        <button class="btn btn-danger btn-sm btn-icon" onclick="handleRemoveSpamList('${type}', ${jsAttrString(entry)})">×</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            tbody.innerHTML = `<tr><td colspan="2" style="text-align: center; color: var(--color-muted);">No ${type} entries</td></tr>`;
        }
        tbody.dataset.loaded = "true";
    };

    await fetchCachedList({
        url: `/api/domains/${domain}/spam/${type}`,
        tbody, card, force, firstLoad, render,
        loadingHtml: `<tr><td colspan="2" style="text-align: center; color: var(--color-muted);">Loading ${type}...</td></tr>`,
        errorHtml: `<tr><td colspan="2" style="text-align: center; color: var(--danger);">Error loading ${type}</td></tr>`,
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

// Remove Whitelist/Blacklist Entry
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


// --- 6. Global Domain Selector Initialization ---
async function initDomainDropdowns() {
    const select = document.getElementById("global-domain-select");
    
    try {
        const result = await cachedFetch("/api/domains");
        select.innerHTML = "";
        
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
        select.innerHTML = '<option value="">Error loading domains</option>';
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

// 5.8 Access Control & Delegations UI handlers
function validateLocalUserIdentifier(identifier) {
    if (/^[a-zA-Z0-9._-]+$/.test(identifier)) return true;
    if (/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(identifier)) return true;
    if (/^[a-zA-Z0-9._-]+@[a-zA-Z0-9-]+$/.test(identifier)) return true;
    return false;
}

function isLocalLoginUser(identifier) {
    const isPlainUsername = /^[a-zA-Z0-9._-]+$/.test(identifier);
    if (isPlainUsername) return true;
    const isStrictEmail = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(identifier);
    if (isStrictEmail && oidcEnabled) return false;
    return true;
}

function delegationPasswordRequired(identifier) {
    if (!isLocalLoginUser(identifier)) return false;
    return !knownDelegationUsers.has(identifier.toLowerCase());
}

function updateDelegationPasswordHint() {
    const emailInput = document.getElementById("delegation-email");
    const passInput = document.getElementById("delegation-password");
    const requiredMarker = document.getElementById("delegation-password-required");
    const hint = document.getElementById("delegation-password-hint");
    if (!emailInput || !passInput || !requiredMarker || !hint) return;

    const identifier = emailInput.value.trim().toLowerCase();
    const required = identifier && delegationPasswordRequired(identifier);

    requiredMarker.style.display = required ? "inline" : "none";
    passInput.required = required;

    if (!identifier) {
        hint.textContent = "Required for new local users. Optional for OIDC email accounts or when editing an existing user.";
    } else if (required) {
        hint.textContent = "A password is required because this user signs in locally.";
    } else if (isLocalLoginUser(identifier)) {
        hint.textContent = "Leave blank to keep the current password for this local user.";
    } else {
        hint.textContent = "Optional for OIDC users who sign in through your identity provider.";
    }
}

async function loadDelegationsPage(options = {}) {
    const listBody = document.getElementById("delegations-list-tbody");
    listBody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">Querying access delegations...</td></tr>';
    
    const checklist = document.getElementById("delegation-domains-checklist");
    checklist.innerHTML = '<div style="color: var(--color-muted); font-size: 0.9rem;">Loading available domains...</div>';
    
    try {
        const [domainsRes, delegationsRes] = await Promise.all([
            apiRequest("/api/domains"),
            apiRequest("/api/admin/delegations"),
        ]);

        if (delegationsRes?.permissions?.length) {
            delegationPermissionCatalog = delegationsRes.permissions;
        }

        if (domainsRes.success && domainsRes.data) {
            checklist.innerHTML = "";

            const adminRow = document.createElement("label");
            adminRow.className = "delegation-admin-option flex-row align-center";
            adminRow.innerHTML = `
                <input type="checkbox" id="delegation-admin-cb" name="delegated-domain-cb" value="*" style="width: auto; height: auto; margin: 0;">
                <span>Admin (full access to all domains and settings)</span>
            `;
            checklist.appendChild(adminRow);

            const matrix = document.createElement("div");
            matrix.id = "delegation-permissions-matrix";
            matrix.className = "delegation-permissions-matrix";

            if (domainsRes.data.length > 0) {
                domainsRes.data.forEach(domain => {
                    matrix.appendChild(createDelegationDomainRow(domain));
                });
            } else {
                matrix.innerHTML = '<div style="color: var(--color-muted); font-size: 0.9rem;">No domains available yet.</div>';
            }
            checklist.appendChild(matrix);

            document.getElementById("delegation-admin-cb").addEventListener("change", (event) => {
                matrix.style.display = event.target.checked ? "none" : "flex";
            });
        }
        
        listBody.innerHTML = "";
        knownDelegationUsers = new Set();

        if (delegationsRes.success && delegationsRes.data && delegationsRes.data.length > 0) {
            delegationsRes.data.forEach(item => {
                knownDelegationUsers.add(item.email.toLowerCase());
                const tr = document.createElement("tr");
                
                let domainsStr = "";
                if (item.is_admin || item.domains.includes("*")) {
                    domainsStr = '<span style="color: var(--accent); font-weight: 600;">Admin</span>';
                } else if (item.grants && item.grants.length > 0) {
                    domainsStr = item.grants.map(grant => {
                        const labels = (grant.permissions || [])
                            .map(perm => DELEGATION_PERMISSION_LABELS[perm] || perm)
                            .join(", ");
                        return `<div><strong>${escapeHtml(grant.domain)}</strong><br><span style="color: var(--color-secondary); font-size: 0.8rem;">${escapeHtml(labels || "No permissions")}</span></div>`;
                    }).join('<div style="margin-top: 0.5rem;"></div>');
                } else if (item.domains.length > 0) {
                    domainsStr = item.domains.filter(d => d !== "*").map(escapeHtml).join(", ");
                } else {
                    domainsStr = '<span style="color: var(--color-muted); font-style: italic;">None</span>';
                }
                
                const emailTd = document.createElement("td");
                const emailStrong = document.createElement("strong");
                emailStrong.textContent = item.email;
                emailTd.appendChild(emailStrong);
                if (item.notification_email && item.notification_email !== item.email) {
                    const contactLine = document.createElement("div");
                    contactLine.style.fontSize = "0.75rem";
                    contactLine.style.color = "var(--color-secondary)";
                    contactLine.style.marginTop = "0.25rem";
                    contactLine.textContent = `Contact: ${item.notification_email}`;
                    emailTd.appendChild(contactLine);
                } else if (item.notification_email) {
                    const contactLine = document.createElement("div");
                    contactLine.style.fontSize = "0.75rem";
                    contactLine.style.color = "var(--color-secondary)";
                    contactLine.style.marginTop = "0.25rem";
                    contactLine.textContent = "Contact: email login";
                    emailTd.appendChild(contactLine);
                }
                tr.appendChild(emailTd);
                
                const domainsTd = document.createElement("td");
                domainsTd.style.maxWidth = "360px";
                domainsTd.style.wordBreak = "break-word";
                domainsTd.innerHTML = domainsStr;
                tr.appendChild(domainsTd);
                
                const actionTd = document.createElement("td");
                actionTd.style.textAlign = "right";
                
                const wrapper = document.createElement("div");
                wrapper.className = "flex-row";
                wrapper.style.justifyContent = "flex-end";
                wrapper.style.gap = "0.5rem";
                
                const editBtn = document.createElement("button");
                editBtn.className = "btn btn-secondary btn-sm";
                editBtn.innerHTML = btnLabel("gear", "Edit");
                editBtn.addEventListener("click", () => {
                    handleEditDelegation(
                        item.email,
                        item.grants || [],
                        item.is_admin || item.domains.includes("*"),
                        item.contact_email || ""
                    );
                });
                wrapper.appendChild(editBtn);
                
                const revokeBtn = document.createElement("button");
                revokeBtn.className = "btn btn-danger btn-sm";
                revokeBtn.innerHTML = "Revoke";
                if (currentUser && currentUser.email.toLowerCase() === item.email.toLowerCase()) {
                    revokeBtn.disabled = true;
                    revokeBtn.title = "You cannot revoke your own access.";
                    revokeBtn.style.opacity = "0.5";
                    revokeBtn.style.cursor = "not-allowed";
                } else {
                    revokeBtn.addEventListener("click", () => {
                        handleDeleteDelegation(item.email);
                    });
                }
                wrapper.appendChild(revokeBtn);
                
                actionTd.appendChild(wrapper);
                tr.appendChild(actionTd);
                listBody.appendChild(tr);
            });
        } else {
            listBody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">No delegations configured yet.</td></tr>';
        }
        updateDelegationPasswordHint();
    } catch (err) {
        listBody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--danger);">Failed to load delegations: ${escapeHtml(err.message)}</td></tr>`;
        checklist.innerHTML = `<div style="color: var(--danger); font-size: 0.9rem;">Failed to load domains: ${escapeHtml(err.message)}</div>`;
    }
}

function createDelegationDomainRow(domain) {
    const row = document.createElement("div");
    row.className = "delegation-domain-row";
    row.dataset.domain = domain;

    const permissionMarkup = delegationPermissionCatalog.map(permission => `
        <label class="delegation-permission-option">
            <input type="checkbox" class="delegation-permission-cb" value="${escapeHtml(permission)}" checked>
            <span>${escapeHtml(DELEGATION_PERMISSION_LABELS[permission] || permission)}</span>
        </label>
    `).join("");

    row.innerHTML = `
        <label class="delegation-domain-toggle flex-row align-center">
            <input type="checkbox" class="delegation-domain-enable" value="${escapeHtml(domain)}" style="width: auto; height: auto; margin: 0;">
            <strong>${escapeHtml(domain)}</strong>
        </label>
        <div class="delegation-permission-grid">${permissionMarkup}</div>
    `;

    const enableCb = row.querySelector(".delegation-domain-enable");
    const permissionGrid = row.querySelector(".delegation-permission-grid");
    enableCb.addEventListener("change", () => {
        permissionGrid.style.display = enableCb.checked ? "grid" : "none";
    });
    permissionGrid.style.display = "none";
    return row;
}

function collectDelegationGrants() {
    const grants = [];
    document.querySelectorAll(".delegation-domain-row").forEach(row => {
        const enableCb = row.querySelector(".delegation-domain-enable");
        if (!enableCb?.checked) return;
        const permissions = [...row.querySelectorAll(".delegation-permission-cb:checked")].map(cb => cb.value);
        grants.push({ domain: enableCb.value, permissions });
    });
    return grants;
}

function handleEditDelegation(email, grants, isAdmin, contactEmail = "") {
    document.getElementById("delegation-email").value = email;
    const contactInput = document.getElementById("delegation-contact-email");
    if (contactInput) contactInput.value = contactEmail || "";
    const passInput = document.getElementById("delegation-password");
    if (passInput) passInput.value = "";

    const adminCb = document.getElementById("delegation-admin-cb");
    const matrix = document.getElementById("delegation-permissions-matrix");
    document.querySelectorAll(".delegation-domain-row").forEach(row => {
        const enableCb = row.querySelector(".delegation-domain-enable");
        const permissionGrid = row.querySelector(".delegation-permission-grid");
        enableCb.checked = false;
        row.querySelectorAll(".delegation-permission-cb").forEach(cb => {
            cb.checked = true;
        });
        permissionGrid.style.display = "none";
    });

    if (adminCb) {
        adminCb.checked = !!isAdmin;
        if (matrix) matrix.style.display = isAdmin ? "none" : "flex";
    }

    if (!isAdmin) {
        const grantMap = Object.fromEntries((grants || []).map(grant => [grant.domain, grant.permissions || []]));
        document.querySelectorAll(".delegation-domain-row").forEach(row => {
            const domain = row.dataset.domain;
            const enableCb = row.querySelector(".delegation-domain-enable");
            const permissionGrid = row.querySelector(".delegation-permission-grid");
            const selected = grantMap[domain];
            if (!selected) return;
            enableCb.checked = true;
            permissionGrid.style.display = "grid";
            row.querySelectorAll(".delegation-permission-cb").forEach(cb => {
                cb.checked = selected.includes(cb.value);
            });
        });
    }

    updateDelegationPasswordHint();
    document.getElementById("form-create-delegation").scrollIntoView({ behavior: "smooth" });
}

window.handleEditDelegation = handleEditDelegation;

async function handleDeleteDelegation(email) {
    const confirmed = await showTypedConfirm({
        title: "Revoke Access",
        message: `Revoke all access rights for ${email}? They will no longer be able to sign in.`,
        expectedValue: email,
        confirmLabel: "Revoke Access",
        inputLabel: "Type the user's email address to confirm"
    });
    if (!confirmed) return;

    try {
        await apiRequest(`/api/admin/delegations?email=${encodeURIComponent(email)}`, "DELETE");
        showAlert("success", `Access rights revoked for ${email}.`);
        await loadDelegationsPage();
    } catch (err) {
        showAlert("error", err.message);
    }
}

window.handleDeleteDelegation = handleDeleteDelegation;

document.getElementById("form-create-delegation").addEventListener("submit", async (e) => {
    e.preventDefault();
    const emailInput = document.getElementById("delegation-email");
    const contactInput = document.getElementById("delegation-contact-email");
    const email = emailInput.value.trim().toLowerCase();
    const contactEmail = contactInput ? contactInput.value.trim().toLowerCase() : "";
    const passInput = document.getElementById("delegation-password");
    const password = passInput ? passInput.value : "";
    const adminCb = document.getElementById("delegation-admin-cb");
    const isAdmin = !!adminCb?.checked;
    const grants = collectDelegationGrants();
    
    if (!email) return;
    if (!validateLocalUserIdentifier(email)) {
        showAlert("error", "Invalid user identifier. Use a username (e.g. billy), user@local, or email address.");
        return;
    }
    if (delegationPasswordRequired(email) && !password.trim()) {
        showAlert("error", "Password is required when creating a local user.");
        return;
    }
    if (!isAdmin && grants.length === 0) {
        showAlert("error", "Select at least one domain with permissions, or grant Admin access.");
        return;
    }
    if (!isAdmin && grants.some(grant => grant.permissions.length === 0)) {
        showAlert("error", "Each selected domain needs at least one permission.");
        return;
    }
    
    try {
        const payload = {
            email,
            contact_email: contactEmail || null,
            domains: isAdmin ? ["*"] : grants.map(grant => grant.domain),
            grants: isAdmin ? [] : grants,
        };
        if (password) payload.password = password;
        
        await apiRequest("/api/admin/delegations", "POST", payload);
        showAlert("success", `Permissions updated for ${email}.`);
        emailInput.value = "";
        if (contactInput) contactInput.value = "";
        if (passInput) passInput.value = "";
        if (adminCb) adminCb.checked = false;
        document.getElementById("delegation-permissions-matrix")?.style.setProperty("display", "flex");
        document.querySelectorAll(".delegation-domain-row").forEach(row => {
            row.querySelector(".delegation-domain-enable").checked = false;
            row.querySelector(".delegation-permission-grid").style.display = "none";
            row.querySelectorAll(".delegation-permission-cb").forEach(cb => { cb.checked = true; });
        });
        await loadDelegationsPage();
    } catch (err) {
        showAlert("error", err.message);
    }
});

// On DOM Loaded
document.addEventListener("DOMContentLoaded", async () => {
    initConfirmModals();

    const refreshDnsHealthBtn = document.getElementById("btn-refresh-dns-health");
    if (refreshDnsHealthBtn) {
        refreshDnsHealthBtn.addEventListener("click", async () => {
            if (!activeDomain) {
                showAlert("warning", "Select a domain first.");
                return;
            }
            refreshDnsHealthBtn.disabled = true;
            refreshDnsHealthBtn.innerHTML = btnLabel("arrow-clockwise", "Checking...", true);
            try {
                await loadDnsHealth(activeDomain, { force: true });
                showAlert("success", "DNS health rechecked.");
            } catch (err) {
                showAlert("error", err.message);
            } finally {
                refreshDnsHealthBtn.innerHTML = btnLabel("arrow-clockwise", "Recheck DNS");
                refreshDnsHealthBtn.disabled = false;
            }
        });
    }

    const refreshDomainsStatusBtn = document.getElementById("btn-refresh-domains-status");
    if (refreshDomainsStatusBtn) {
        refreshDomainsStatusBtn.addEventListener("click", () => refreshDomainsListStatus());
    }

    // 1. Fetch current user context
    try {
        const meResult = await apiRequest("/api/me");
        if (meResult && meResult.success) {
            currentUser = meResult.user;
            oidcEnabled = !!meResult.oidc_enabled;
            
            if (currentUser) {
                // Update User Profile UI details
                document.getElementById("user-email").textContent = currentUser.email;
                const roleBadge = document.getElementById("user-role-badge");
                roleBadge.textContent = currentUser.is_admin ? "Admin" : "User";
                roleBadge.style.background = currentUser.is_admin
                    ? `rgba(var(--accent-rgb), 0.2)`
                    : "rgba(99, 102, 241, 0.2)";
                roleBadge.style.color = currentUser.is_admin ? "var(--accent)" : "#a5b4fc";
                document.getElementById("user-profile-container").style.display = "block";
                applyUserPermissionsUI();
            }
        }
    } catch (e) {
        console.warn("Could not retrieve user OIDC profile:", e);
    }

    // 2. Fetch overall quotas (if admin)
    if (currentUser?.is_admin) {
        await loadAccountQuota();
    }
    
    // 3. Populate domains dropdown
    await initDomainDropdowns();
    initResetPortal();
    
    // 4. Domain DNS wizard (admin or users with dns permission)
    const canManageDns = currentUser?.is_admin || getUserPermissionUnion().has("dns");
    if (canManageDns) {
        initSetupWizard();
        applyDomainsSectionVisibility();
        if (currentUser?.is_admin) {
            try {
                const cfStatus = await apiRequest("/api/cloudflare/status");
                setupCfConfigured = !!(cfStatus && cfStatus.configured);
                const cfMissing = document.getElementById("setup-cf-missing");
                if (cfMissing) {
                    cfMissing.style.display = setupCfConfigured ? "none" : "block";
                }
                if (setupWizardStep === 2 && setupCurrentHealth) {
                    renderSetupDnsChecks(setupCurrentHealth);
                }
            } catch (e) {
                console.warn("Could not retrieve Cloudflare integration status:", e);
            }
        }
    }

    // 5. Load Active Theme Preference
    loadTheme();

    // 6. Setup theme select card event listeners
    document.querySelectorAll(".theme-select-card").forEach(card => {
        card.addEventListener("click", () => {
            const theme = card.getAttribute("data-theme");
            setTheme(theme);
            showAlert("success", `Workspace theme changed to ${card.querySelector("div:last-child").textContent}`);
        });
    });

    // 7. Setup system settings form submission listener
    const settingsForm = document.getElementById("form-system-settings");
    if (settingsForm) {
        settingsForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const submitBtn = document.getElementById("btn-save-system-settings");
            submitBtn.disabled = true;
            submitBtn.innerHTML = btnLabel("save", "Saving Settings...", true);
            
            const payload = {
                OIDC_ENABLED: document.getElementById("setting-oidc-enabled").value,
                OIDC_SCOPES: document.getElementById("setting-oidc-scopes").value.trim(),
                OIDC_DISCOVERY_URL: document.getElementById("setting-oidc-discovery-url").value.trim(),
                OIDC_REDIRECT_URI: document.getElementById("setting-oidc-redirect-uri").value.trim(),
                OIDC_CLIENT_ID: document.getElementById("setting-oidc-client-id").value.trim(),
                OIDC_ADMIN_USERS: document.getElementById("setting-oidc-admin-users").value.trim(),
                OIDC_ADMIN_GROUP: document.getElementById("setting-oidc-admin-group").value.trim(),
                MX_SERVER: document.getElementById("setting-mx-server").value.trim(),
                MX_USER: document.getElementById("setting-mx-user").value.trim(),
                CF_ACCOUNT_ID: document.getElementById("setting-cf-account-id").value.trim(),
                ADMIN_USER: document.getElementById("setting-admin-user").value.trim(),
                MAILBOX_RESET_ENABLED: document.getElementById("setting-mailbox-reset-enabled").value,
                RESET_SMTP_HOST: document.getElementById("setting-reset-smtp-host").value.trim(),
                RESET_SMTP_PORT: document.getElementById("setting-reset-smtp-port").value.trim(),
                RESET_SMTP_USER: document.getElementById("setting-reset-smtp-user").value.trim(),
                RESET_SMTP_FROM: document.getElementById("setting-reset-smtp-from").value.trim(),
                RESET_SMTP_USE_TLS: document.getElementById("setting-reset-smtp-use-tls").value,
            };

            const newAdminPassword = document.getElementById("setting-admin-password").value;
            if (newAdminPassword.trim()) {
                payload.ADMIN_PASSWORD = newAdminPassword;
            }

            const newSmtpPassword = document.getElementById("setting-reset-smtp-password").value;
            if (newSmtpPassword.trim()) {
                payload.RESET_SMTP_PASSWORD = newSmtpPassword;
            }
            
            try {
                const contactSaved = await saveAdminContactEmail();
                if (!contactSaved) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = btnLabel("save", "Save System Settings");
                    return;
                }

                const res = await apiRequest("/api/admin/settings", "POST", payload);
                if (res.success) {
                    showAlert("success", "System settings successfully updated!");
                    document.getElementById("setting-admin-password").value = "";
                    document.getElementById("setting-reset-smtp-password").value = "";
                    await loadSettingsPage();
                } else {
                    showAlert("error", res.error.message || "Failed to update system settings.");
                }
            } catch (err) {
                showAlert("error", `Error updating settings: ${err.message}`);
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = btnLabel("save", "Save System Settings");
            }
        });
    }

    const testSmtpBtn = document.getElementById("btn-test-smtp-settings");
    if (testSmtpBtn) {
        testSmtpBtn.addEventListener("click", async () => {
            testSmtpBtn.disabled = true;
            testSmtpBtn.innerHTML = btnLabel("send", "Sending...", true);
            try {
                const contactSaved = await saveAdminContactEmail();
                if (!contactSaved) return;

                const result = await apiRequest("/api/admin/settings/test-smtp", "POST", collectSmtpTestPayload());
                if (result.success) {
                    showAlert("success", result.message || "Test email sent.");
                } else {
                    showAlert("error", result.error?.message || "Failed to send test email.");
                }
            } catch (err) {
                showAlert("error", err.message);
            } finally {
                testSmtpBtn.innerHTML = btnLabel("send", "Send Test Email");
                renderSmtpTestStatus(currentUser);
            }
        });
    }
});

// --- 7. Theming & Settings Controller ---

function loadTheme() {
    const activeTheme = localStorage.getItem("workspace-theme") || "emerald";
    setTheme(activeTheme, false);
}

function setTheme(theme, save = true) {
    const themes = window.Mxm?.themes?.THEME_IDS ?? [
        "emerald", "indigo", "crimson", "amber", "amethyst", "cyberpunk",
        "emerald-light", "indigo-light", "slate-light", "rose-light",
    ];
    const safeTheme = themes.includes(theme) ? theme : "emerald";
    
    // Remove all theme classes from body
    themes.forEach(t => document.body.classList.remove(`theme-${t}`));
    
    // Apply selected theme class
    document.body.classList.add(`theme-${safeTheme}`);
    
    if (save) {
        localStorage.setItem("workspace-theme", safeTheme);
    }
    
    // Highlight selected card if settings page is loaded
    document.querySelectorAll(".theme-select-card").forEach(card => {
        if (card.getAttribute("data-theme") === safeTheme) {
            card.classList.add("active");
        } else {
            card.classList.remove("active");
        }
    });

    if (typeof updateThemedFavicon === "function") {
        updateThemedFavicon();
    }
}

function renderSecretStatus(elementId, configured, successText = "Configured via environment") {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.innerHTML = configured
        ? `<span class="status-indicator success"><span class="dot"></span> ${escapeHtml(successText)}</span>`
        : `<span class="status-indicator danger"><span class="dot"></span> Not configured</span>`;
}

function renderSmtpTestStatus(user) {
    const statusEl = document.getElementById("setting-smtp-test-status");
    const testBtn = document.getElementById("btn-test-smtp-settings");
    if (!statusEl || !testBtn) return;

    const notificationEmail = user?.notification_email;
    if (notificationEmail) {
        statusEl.innerHTML = `<span class="status-indicator success"><span class="dot"></span> Test emails will be sent to <strong>${escapeHtml(notificationEmail)}</strong></span>`;
        testBtn.disabled = false;
    } else {
        statusEl.innerHTML = `<span class="status-indicator danger"><span class="dot"></span> Add a contact email below (or sign in with an email address) to send test emails.</span>`;
        testBtn.disabled = true;
    }
}

function collectSmtpTestPayload() {
    const payload = {
        RESET_SMTP_HOST: document.getElementById("setting-reset-smtp-host").value.trim(),
        RESET_SMTP_PORT: document.getElementById("setting-reset-smtp-port").value.trim(),
        RESET_SMTP_USER: document.getElementById("setting-reset-smtp-user").value.trim(),
        RESET_SMTP_FROM: document.getElementById("setting-reset-smtp-from").value.trim(),
        RESET_SMTP_USE_TLS: document.getElementById("setting-reset-smtp-use-tls").value,
    };
    const smtpPassword = document.getElementById("setting-reset-smtp-password").value;
    if (smtpPassword.trim()) {
        payload.RESET_SMTP_PASSWORD = smtpPassword;
    }
    return payload;
}

async function saveAdminContactEmail() {
    const input = document.getElementById("setting-admin-contact-email");
    if (!input) return true;

    const nextValue = input.value.trim().toLowerCase();
    const currentValue = (currentUser?.contact_email || "").toLowerCase();
    if (nextValue === currentValue) return true;

    const result = await apiRequest("/api/me/profile", "PATCH", {
        contact_email: nextValue || null,
    });
    if (result?.success) {
        currentUser = {
            ...currentUser,
            contact_email: result.data?.contact_email || null,
            notification_email: result.data?.notification_email || null,
        };
        renderSmtpTestStatus(currentUser);
        return true;
    }
    showAlert("error", result?.error?.message || "Failed to save contact email.");
    return false;
}

async function loadSettingsPage() {
    // Refresh theme active selector highlighted state
    const activeTheme = localStorage.getItem("workspace-theme") || "emerald";
    setTheme(activeTheme, false);
    
    if (currentUser && currentUser.is_admin) {
        document.getElementById("system-settings-card").style.display = "block";
        
        try {
            const res = await apiRequest("/api/admin/settings");
            if (res.success && res.data) {
                const settings = res.data;
                
                // Populate forms
                document.getElementById("setting-oidc-enabled").value = settings.OIDC_ENABLED || "true";
                document.getElementById("setting-oidc-scopes").value = settings.OIDC_SCOPES || "openid email profile groups";
                document.getElementById("setting-oidc-discovery-url").value = settings.OIDC_DISCOVERY_URL || "";
                document.getElementById("setting-oidc-redirect-uri").value = settings.OIDC_REDIRECT_URI || "";
                document.getElementById("setting-oidc-client-id").value = settings.OIDC_CLIENT_ID || "";
                renderSecretStatus("setting-oidc-client-secret-status", settings.OIDC_CLIENT_SECRET_configured);
                document.getElementById("setting-oidc-admin-users").value = settings.OIDC_ADMIN_USERS || "";
                document.getElementById("setting-oidc-admin-group").value = settings.OIDC_ADMIN_GROUP || "administrators";
                
                document.getElementById("setting-mx-server").value = settings.MX_SERVER || "";
                document.getElementById("setting-mx-user").value = settings.MX_USER || "";
                renderSecretStatus("setting-mx-api-key-status", settings.MX_API_KEY_configured);
                
                renderSecretStatus("setting-cf-api-token-status", settings.CF_API_TOKEN_configured);
                document.getElementById("setting-cf-account-id").value = settings.CF_ACCOUNT_ID || "";
                
                document.getElementById("setting-admin-user").value = settings.ADMIN_USER || "admin";
                document.getElementById("setting-admin-password").value = "";

                document.getElementById("setting-mailbox-reset-enabled").value = settings.MAILBOX_RESET_ENABLED || "false";
                document.getElementById("setting-reset-smtp-host").value = settings.RESET_SMTP_HOST || "";
                document.getElementById("setting-reset-smtp-port").value = settings.RESET_SMTP_PORT || "587";
                document.getElementById("setting-reset-smtp-user").value = settings.RESET_SMTP_USER || "";
                document.getElementById("setting-reset-smtp-from").value = settings.RESET_SMTP_FROM || "";
                document.getElementById("setting-reset-smtp-use-tls").value = settings.RESET_SMTP_USE_TLS || "true";
                document.getElementById("setting-reset-smtp-password").value = "";
                renderSecretStatus(
                    "setting-reset-smtp-password-status",
                    settings.RESET_SMTP_PASSWORD_configured,
                    "Password saved"
                );

                const contactInput = document.getElementById("setting-admin-contact-email");
                if (contactInput) {
                    contactInput.value = currentUser?.contact_email || "";
                }
                renderSmtpTestStatus(currentUser);
            }
        } catch (err) {
            showAlert("error", `Failed to load settings: ${err.message}`);
        }
    } else {
        document.getElementById("system-settings-card").style.display = "none";
    }
}


// --- 5.10 System Logs Tab Panel Logic ---
let logAutoRefreshInterval = null;
let logsCache = [];

async function loadLogsPage() {
    if (!currentUser || !currentUser.is_admin) return;

    const dateSelect = document.getElementById("logs-date-select");
    const limitSelect = document.getElementById("logs-limit-select");

    const selectedDate = dateSelect.value || "";
    const selectedLimit = limitSelect.value || "100";

    try {
        const url = `/api/admin/logs?date=${encodeURIComponent(selectedDate)}&limit=${encodeURIComponent(selectedLimit)}`;
        const res = await apiRequest(url);

        if (res.success && res.data) {
            logsCache = res.data.entries || [];
            const availableDates = res.data.available_dates || [];
            const currentDate = res.data.current_date || "";

            // Populate date selection dropdown if not already populated or if list changed
            const existingOptions = Array.from(dateSelect.options).map(o => o.value);
            const matchesAvailable = availableDates.length === existingOptions.length && availableDates.every((v, i) => v === existingOptions[i]);

            if (!matchesAvailable) {
                dateSelect.innerHTML = "";
                availableDates.forEach(dateVal => {
                    const opt = document.createElement("option");
                    opt.value = dateVal;
                    opt.textContent = dateVal;
                    if (dateVal === currentDate) {
                        opt.selected = true;
                    }
                    dateSelect.appendChild(opt);
                });
            }

            renderLogsTable();
        }
    } catch (err) {
        console.error("Failed to load logs:", err);
        showAlert("error", `Failed to retrieve logs: ${err.message}`);
    }
}

function renderLogsTable() {
    const tbody = document.getElementById("logs-list-tbody");
    const filterQuery = document.getElementById("logs-search").value.trim().toLowerCase();

    tbody.innerHTML = "";

    const filteredLogs = logsCache.filter(log => {
        if (!filterQuery) return true;
        const detailsStr = JSON.stringify(log.details || {}).toLowerCase();
        return (
            (log.timestamp || "").toLowerCase().includes(filterQuery) ||
            (log.user || "").toLowerCase().includes(filterQuery) ||
            (log.action || "").toLowerCase().includes(filterQuery) ||
            (log.target || "").toLowerCase().includes(filterQuery) ||
            detailsStr.includes(filterQuery)
        );
    });

    if (filteredLogs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--color-muted); padding: 2rem;">No matching log entries found.</td></tr>`;
        return;
    }

    filteredLogs.forEach(log => {
        const tr = document.createElement("tr");

        // Format ISO timestamp slightly
        let formattedTime = log.timestamp || "";
        try {
            const dt = new Date(log.timestamp);
            if (!isNaN(dt)) {
                formattedTime = dt.toISOString().replace("T", " ").substring(0, 19);
            }
        } catch (_) {}

        tr.innerHTML = `
            <td><code>${escapeHtml(formattedTime)}</code></td>
            <td><strong>${escapeHtml(log.user)}</strong></td>
            <td><span class="badge" style="font-size: 0.8rem; font-weight: 500; font-family: monospace; background: rgba(255,255,255,0.05); padding: 0.15rem 0.4rem; border-radius: 4px;">${escapeHtml(log.action)}</span></td>
            <td><code style="word-break: break-all;">${escapeHtml(log.target)}</code></td>
            <td><pre style="font-size: 0.75rem; margin: 0; background: rgba(0,0,0,0.2); padding: 0.4rem; border-radius: 6px; overflow-x: auto; white-space: pre-wrap; font-family: monospace; color: var(--color-secondary); max-width: 500px;">${escapeHtml(JSON.stringify(log.details))}</pre></td>
        `;
        tbody.appendChild(tr);
    });
}

// Initialize log page event handlers
function initLogsPageEvents() {
    const dateSelect = document.getElementById("logs-date-select");
    const limitSelect = document.getElementById("logs-limit-select");
    const searchInput = document.getElementById("logs-search");
    const autoRefreshCheckbox = document.getElementById("logs-auto-refresh");
    const refreshBtn = document.getElementById("btn-refresh-logs");

    if (!dateSelect || !limitSelect || !searchInput || !autoRefreshCheckbox || !refreshBtn) return;

    dateSelect.addEventListener("change", loadLogsPage);
    limitSelect.addEventListener("change", loadLogsPage);
    searchInput.addEventListener("input", renderLogsTable);

    refreshBtn.addEventListener("click", async () => {
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = btnLabel("arrow-clockwise", "Loading...", true);
        try {
            await loadLogsPage();
        } finally {
            refreshBtn.innerHTML = btnLabel("arrow-clockwise", "Reload Logs");
            refreshBtn.disabled = false;
        }
    });

    autoRefreshCheckbox.addEventListener("change", () => {
        if (autoRefreshCheckbox.checked) {
            setupLogsAutoRefresh();
        } else {
            clearLogsAutoRefresh();
        }
    });

    // Clear auto refresh interval if tab is changed
    document.querySelectorAll(".nav-item").forEach(item => {
        item.addEventListener("click", () => {
            const tab = item.getAttribute("data-tab");
            if (tab !== "logs") {
                autoRefreshCheckbox.checked = false;
                clearLogsAutoRefresh();
            }
        });
    });
}

function setupLogsAutoRefresh() {
    clearLogsAutoRefresh();
    logAutoRefreshInterval = setInterval(async () => {
        const activeTab = document.querySelector(".nav-item.active")?.getAttribute("data-tab");
        if (activeTab === "logs") {
            await loadLogsPage();
        } else {
            clearLogsAutoRefresh();
        }
    }, 10000);
}

function clearLogsAutoRefresh() {
    if (logAutoRefreshInterval) {
        clearInterval(logAutoRefreshInterval);
        logAutoRefreshInterval = null;
    }
}

// Register Events
initLogsPageEvents();

document.getElementById("delegation-email")?.addEventListener("input", updateDelegationPasswordHint);
document.getElementById("delegation-password")?.addEventListener("input", updateDelegationPasswordHint);