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
    return `${bi(iconName, spin)} ${escapeHtml(text)}`;
}

let pendingApiActivity = 0;

function setApiActivityActive(active) {
    const bar = document.getElementById("ui-activity-bar");
    if (!bar) return;
    bar.hidden = !active;
    bar.classList.toggle("is-active", active);
    bar.setAttribute("aria-hidden", active ? "false" : "true");
}

function bumpApiActivity(delta) {
    pendingApiActivity = Math.max(0, pendingApiActivity + delta);
    setApiActivityActive(pendingApiActivity > 0);
}

function loadingRowHtml(colspan, text) {
    return `<tr><td colspan="${colspan}" style="text-align: center; color: var(--color-muted);">${escapeHtml(text)}</td></tr>`;
}

function rememberBtnIdle(btn) {
    if (btn && !btn.dataset.idleHtml) {
        btn.dataset.idleHtml = btn.innerHTML;
    }
}

function restoreBtnIdle(btn) {
    if (!btn?.dataset.idleHtml) return;
    setTrustedHtml(btn, btn.dataset.idleHtml);
    delete btn.dataset.idleHtml;
}

function setBtnLoading(btn, loading, { icon = "arrow-clockwise", text = "Working..." } = {}) {
    if (!btn) return;
    if (loading) {
        rememberBtnIdle(btn);
        btn.disabled = true;
        setTrustedHtml(btn, btnLabel(icon, text, true));
        btn.setAttribute("aria-busy", "true");
        return;
    }
    btn.disabled = false;
    restoreBtnIdle(btn);
    btn.removeAttribute("aria-busy");
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
    // Adding a new domain registers it on MXroute, which is admin-only.
    const wizard = document.getElementById("domain-setup-wizard");
    if (wizard) wizard.style.display = isAdmin ? "" : "none";
    updateBulkFixDnsButtonVisibility();
}

function updateBulkFixDnsButtonVisibility() {
    const btn = document.getElementById("btn-bulk-fix-dns");
    if (!btn) return;
    if (!currentUser?.is_admin) {
        btn.style.display = "none";
        return;
    }
    const hasUnhealthy = [...domainRowCache.values()].some((row) => row.fixDnsVisible);
    btn.style.display = hasUnhealthy ? "" : "none";
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
        notifications: document.getElementById("nav-tab-notifications"),
        settings: document.getElementById("nav-tab-settings"),
    };

    if (currentUser.is_admin) {
        Object.values(navTabs).forEach(tab => {
            if (!tab) return;
            if (tab.id === "nav-tab-delegations" || tab.id === "nav-tab-logs" || tab.id === "nav-tab-notifications") {
                tab.style.display = "flex";
            } else {
                tab.style.display = "";
            }
        });
        document.getElementById("sidebar-quota-container").style.display = "";
        document.getElementById("dash-quota-card").style.display = "";
        applyDashboardSectionVisibility();
        return;
    }

    document.getElementById("nav-tab-delegations").style.display = "none";
    document.getElementById("nav-tab-logs").style.display = "none";
    const notificationsTab = document.getElementById("nav-tab-notifications");
    if (notificationsTab) notificationsTab.style.display = "none";
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

function publicOriginHost(host) {
    return `${window.location.protocol}//${host}`;
}

function setTrustedHtml(el, html) {
    if (!el) return;
    el.replaceChildren();
    if (html == null || html === "") return;
    const doc = new DOMParser().parseFromString(html, "text/html");
    el.append(...doc.body.childNodes);
}

function appendTrustedHtml(el, html) {
    if (!el || html == null || html === "") return;
    const doc = new DOMParser().parseFromString(html, "text/html");
    el.append(...doc.body.childNodes);
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

    bumpApiActivity(1);
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
    } finally {
        bumpApiActivity(-1);
    }
}

const apiCache = new Map();
const domainRowCache = new Map();
const backgroundRefreshes = new Map();

