function maskRecoveryEmail(email) {
    if (!email || !email.includes("@")) return "—";
    const [local, domain] = email.split("@");
    if (local.length <= 1) return `*@${domain}`;
    return `${local[0]}${"*".repeat(Math.min(3, local.length - 1))}@${domain}`;
}

function mailboxActionsMenuHtml(account) {
    const username = escapeHtml(account.username);
    const recoveryEmail = escapeHtml(account.recovery_email || "");

    return `
        <div class="action-menu" data-action-menu>
            <button type="button" class="btn btn-secondary btn-sm action-menu-toggle" aria-haspopup="menu" aria-expanded="false">
                ${bi("three-dots-vertical")} Actions
            </button>
            <div class="action-menu-panel" role="menu" hidden>
                <button type="button" class="action-menu-item" role="menuitem"
                    data-action="client-setup" data-username="${username}">
                    ${bi("envelope-at")} Client setup
                </button>
                <button type="button" class="action-menu-item" role="menuitem"
                    data-action="recovery" data-username="${username}" data-recovery-email="${recoveryEmail}">
                    ${bi("envelope")} Recovery email
                </button>
                <button type="button" class="action-menu-item" role="menuitem"
                    data-action="password" data-username="${username}">
                    ${bi("key")} Change password
                </button>
                <button type="button" class="action-menu-item" role="menuitem"
                    data-action="limits" data-username="${username}"
                    data-quota="${Number(account.quota)}" data-limit="${Number(account.limit)}">
                    ${bi("gear")} Limits
                </button>
                <button type="button" class="action-menu-item action-menu-item-danger" role="menuitem"
                    data-action="delete" data-username="${username}">
                    ${bi("trash")} Delete
                </button>
            </div>
        </div>
    `;
}

function initMailboxActionMenus() {
    initTableActionMenus("emails-list-tbody", (item) => {
        const username = item.dataset.username;
        const action = item.dataset.action;
        if (!username || !action) return;

        if (action === "client-setup") {
            openMailClientSetupModal(username);
        } else if (action === "recovery") {
            openRecoveryModal(username, item.dataset.recoveryEmail || "");
        } else if (action === "password") {
            openPasswordModal(username);
        } else if (action === "limits") {
            openQuotaModal(username, Number(item.dataset.quota), Number(item.dataset.limit));
        } else if (action === "delete") {
            handleDeleteEmail(username);
        }
    });
}

function initSecondaryTableActionMenus() {
    initTableActionMenus("forwarders-list-tbody", (item) => {
        if (item.dataset.action === "delete") handleDeleteForwarder(item.dataset.alias);
    });
    initTableActionMenus("pointers-tbody", (item) => {
        if (item.dataset.action === "delete") handleDeletePointer(item.dataset.pointer);
    });
    initTableActionMenus("whitelist-tbody", (item) => {
        if (item.dataset.action === "remove") handleRemoveSpamList("whitelist", item.dataset.entry);
    });
    initTableActionMenus("blacklist-tbody", (item) => {
        if (item.dataset.action === "remove") handleRemoveSpamList("blacklist", item.dataset.entry);
    });
    initTableActionMenus("delegations-list-tbody", (item) => {
        if (item.dataset.action === "edit") {
            let grants = [];
            try {
                grants = JSON.parse(item.dataset.grants || "[]");
            } catch {
                grants = [];
            }
            handleEditDelegation(
                item.dataset.email,
                grants,
                item.dataset.isAdmin === "1",
                item.dataset.contactEmail || ""
            );
        } else if (item.dataset.action === "revoke") {
            handleDeleteDelegation(item.dataset.email);
        }
    });
}

function initDomainActionMenus() {
    initTableActionMenus("domains-list-tbody", (item) => {
        const menu = item.closest("[data-action-menu]");
        const domain = menu?.dataset.domain;
        const action = item.dataset.action;
        if (!domain || !action) return;
        handleDomainAction(domain, action);
    });
}

function handleDomainAction(domain, action) {
    switch (action) {
        case "webmail-open":
            window.open(publicOriginHost(`webmail.${domain}`), "_blank", "noopener");
            return;
        case "fix-dns":
            return handleDomainFixDns(domain);
        case "edit-dmarc":
            return openDomainDmarcModal(domain);
        case "webmail-deploy":
            return handleDomainWebmailDeploy(domain);
        case "toggle-routing":
            return handleDomainToggleRouting(domain);
        case "delete":
            return handleDeleteDomain(domain);
    }
}

async function runDomainDnsFixAlert(domain, payload, { successText, emptyText }) {
    const result = await apiRequest(`/api/domains/${domain}/dns/fix`, "POST", payload);
    const fixed = result.data?.fixed || [];
    showAlert(
        fixed.length ? "success" : "info",
        fixed.length ? successText(fixed, domain) : emptyText(domain)
    );
    invalidateDomainCache(domain);
    await refreshDomainRowDetails(domain, { force: true });
}

async function handleDomainFixDns(domain) {
    try {
        await runDomainDnsFixAlert(domain, {}, {
            successText: (fixed, d) =>
                `Fixed ${fixed.join(", ").toUpperCase()} for ${d}. DNS propagation may take a few minutes.`,
            emptyText: (d) => `No missing records to fix for ${d}.`,
        });
    } catch (err) {
        showAlert("error", err.message);
    }
}

async function handleDomainWebmailDeploy(domain) {
    try {
        await runDomainDnsFixAlert(domain, { records: ["webmail"] }, {
            successText: (_fixed, d) =>
                `Webmail CNAME deployed for ${d}. It may take a few minutes to resolve.`,
            emptyText: (d) =>
                `Webmail for ${d} is already set up or unavailable (check MX_SERVER).`,
        });
    } catch (err) {
        showAlert("error", err.message);
    }
}

async function handleDomainToggleRouting(domain) {
    const cached = domainRowCache.get(domain) || {};
    const nextState = !(cached.mailOn ?? true);
    try {
        await apiRequest(`/api/domains/${domain}/mail-status`, "PATCH", { enabled: nextState });
        showAlert("success", `Mail routing ${nextState ? "enabled" : "disabled"} for ${domain}.`);
        invalidateDomainCache(domain);
        await refreshDomainRowDetails(domain, { force: true });
    } catch (err) {
        showAlert("error", err.message);
    }
}

let mailboxesListAll = [];
let mailboxesListDomain = "";
let mailboxesTableControls = null;

function renderMailboxesTableView(domain) {
    if (!mailboxesTableControls) {
        mailboxesTableControls = mountTableControls("emails-table-controls", {
            storageKey: "mxm-mailboxes-table",
            placeholder: "Search mailboxes…",
            onChange: () => renderMailboxesTableView(mailboxesListDomain),
        });
    }
    if (!mailboxesTableControls) return;

    applyTableView({
        allItems: mailboxesListAll,
        controls: mailboxesTableControls,
        getSearchText: (account) => {
            const address = `${account.username}@${domain}`;
            const recovery = account.recovery_email || "";
            return `${address} ${recovery}`;
        },
        renderItems: (accounts) => {
            renderEmailsList({ success: true, data: accounts }, domain);
        },
    });
}

function renderEmailsList(result, domain) {
    const tbody = document.getElementById("emails-list-tbody");
    setTrustedHtml(tbody, "");

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
                    ${mailboxActionsMenuHtml(account)}
                </td>
            `;
            tbody.appendChild(tr);
        });
    } else {
        const state = mailboxesTableControls?.getState();
        const message = mailboxesListAll.length && state?.query?.trim()
            ? "No mailboxes match your search."
            : "No mailboxes found for this domain.";
        setTrustedHtml(tbody, tablePlaceholderRowHtml(5, message));
    }
    tbody.dataset.loaded = "true";
}

async function loadEmailsList(domain, { force = false } = {}) {
    const tbody = document.getElementById("emails-list-tbody");
    const card = tbody?.closest(".glass-card");
    const firstLoad = !tbody.querySelector("tr[data-username]") && tbody.dataset.loaded !== "true";

    if (domain !== mailboxesListDomain) {
        mailboxesListDomain = domain;
        mailboxesListAll = [];
        mailboxesTableControls?.setState({ query: "", page: 1 });
    }

    await fetchCachedList({
        url: `/api/domains/${domain}/email-accounts`,
        tbody, card, force, firstLoad,
        render: (result) => {
            mailboxesListAll = result?.success && result.data ? result.data : [];
            renderMailboxesTableView(domain);
        },
        loadingHtml: tablePlaceholderRowHtml(5, "Querying mailboxes..."),
        errorHtml: (err) => tablePlaceholderRowHtml(5, `Failed to load email accounts: ${err.message}`, { error: true }),
    });
}

