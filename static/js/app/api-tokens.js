let apiTokenDomainsChecklistReady = false;

function formatApiTokenGrantsHtml(token) {
    if (token.is_admin) {
        return '<span style="color: var(--accent); font-weight: 600;">Admin</span>';
    }
    if (!token.grants?.length) {
        return '<span style="color: var(--color-muted); font-style: italic;">None</span>';
    }
    return token.grants.map((grant) => {
        const labels = (grant.permissions || [])
            .map((perm) => DELEGATION_PERMISSION_LABELS[perm] || perm)
            .join(", ");
        return `<div><strong>${escapeHtml(grant.domain)}</strong><br><span style="color: var(--color-secondary); font-size: 0.8rem;">${escapeHtml(labels || "No permissions")}</span></div>`;
    }).join('<div style="margin-top: 0.5rem;"></div>');
}

function createApiTokenDomainRow(domain) {
    const row = document.createElement("div");
    row.className = "delegation-domain-row api-token-domain-row";
    row.dataset.domain = domain;

    const permissionMarkup = delegationPermissionCatalog.map((permission) => `
        <label class="delegation-permission-option">
            <input type="checkbox" class="api-token-permission-cb" value="${escapeHtml(permission)}" checked>
            <span>${escapeHtml(DELEGATION_PERMISSION_LABELS[permission] || permission)}</span>
        </label>
    `).join("");

    row.innerHTML = `
        <label class="delegation-domain-toggle flex-row align-center">
            <input type="checkbox" class="api-token-domain-enable" value="${escapeHtml(domain)}" style="width: auto; height: auto; margin: 0;">
            <strong>${escapeHtml(domain)}</strong>
        </label>
        <div class="delegation-permission-grid">${permissionMarkup}</div>
    `;

    const enableCb = row.querySelector(".api-token-domain-enable");
    const permissionGrid = row.querySelector(".delegation-permission-grid");
    enableCb.addEventListener("change", () => {
        permissionGrid.style.display = enableCb.checked ? "grid" : "none";
    });
    permissionGrid.style.display = "none";
    return row;
}

function renderApiTokenDomainsChecklist(domainsRes) {
    const checklist = document.getElementById("api-token-domains-checklist");
    if (!checklist) return;

    setTrustedHtml(checklist, "");
    const adminRow = document.createElement("label");
    adminRow.className = "delegation-admin-option flex-row align-center";
    adminRow.innerHTML = `
        <input type="checkbox" id="api-token-admin-cb" style="width: auto; height: auto; margin: 0;">
        <span>Admin (full API access)</span>
    `;
    checklist.appendChild(adminRow);

    const matrix = document.createElement("div");
    matrix.id = "api-token-permissions-matrix";
    matrix.className = "delegation-permissions-matrix";
    if (domainsRes?.success && domainsRes.data?.length) {
        domainsRes.data.forEach((domain) => matrix.appendChild(createApiTokenDomainRow(domain)));
    } else {
        setTrustedHtml(matrix, '<div style="color: var(--color-muted); font-size: 0.9rem;">No domains available yet.</div>');
    }
    checklist.appendChild(matrix);

    document.getElementById("api-token-admin-cb").addEventListener("change", (event) => {
        matrix.style.display = event.target.checked ? "none" : "flex";
    });
    apiTokenDomainsChecklistReady = true;
}

function collectApiTokenGrants() {
    const grants = [];
    document.querySelectorAll(".api-token-domain-row").forEach((row) => {
        const enableCb = row.querySelector(".api-token-domain-enable");
        if (!enableCb?.checked) return;
        const permissions = [...row.querySelectorAll(".api-token-permission-cb:checked")].map((cb) => cb.value);
        grants.push({ domain: enableCb.value, permissions });
    });
    return grants;
}

function resetApiTokenForm() {
    document.getElementById("api-token-label").value = "";
    const adminCb = document.getElementById("api-token-admin-cb");
    if (adminCb) adminCb.checked = false;
    document.getElementById("api-token-permissions-matrix")?.style.setProperty("display", "flex");
    document.querySelectorAll(".api-token-domain-row").forEach((row) => {
        row.querySelector(".api-token-domain-enable").checked = false;
        row.querySelector(".delegation-permission-grid").style.display = "none";
        row.querySelectorAll(".api-token-permission-cb").forEach((cb) => {
            cb.checked = true;
        });
    });
}

function showCreatedApiToken(rawToken) {
    const banner = document.getElementById("api-token-created-banner");
    const valueEl = document.getElementById("api-token-created-value");
    if (!banner || !valueEl) return;
    valueEl.textContent = rawToken;
    banner.style.display = "block";
    banner.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderApiTokensTable(listBody, tokensRes) {
    setTrustedHtml(listBody, "");
    const rows = tokensRes?.success && tokensRes.data ? tokensRes.data : [];
    if (!rows.length) {
        setTrustedHtml(
            listBody,
            '<tr><td colspan="4" style="text-align: center; color: var(--color-muted);">No API tokens yet.</td></tr>',
        );
        return;
    }

    rows.forEach((token) => {
        const tr = document.createElement("tr");
        const labelTd = document.createElement("td");
        const labelStrong = document.createElement("strong");
        labelStrong.textContent = token.label;
        labelTd.appendChild(labelStrong);
        const prefixLine = document.createElement("div");
        prefixLine.style.fontSize = "0.75rem";
        prefixLine.style.color = "var(--color-secondary)";
        prefixLine.style.marginTop = "0.25rem";
        prefixLine.textContent = `${token.token_prefix}…`;
        labelTd.appendChild(prefixLine);

        const grantsTd = document.createElement("td");
        grantsTd.style.maxWidth = "360px";
        grantsTd.style.wordBreak = "break-word";
        setTrustedHtml(grantsTd, formatApiTokenGrantsHtml(token));

        const usedTd = document.createElement("td");
        usedTd.style.fontSize = "0.85rem";
        usedTd.textContent = token.last_used_at
            ? new Date(token.last_used_at).toLocaleString()
            : "Never";

        const actionTd = document.createElement("td");
        actionTd.style.textAlign = "right";
        setTrustedHtml(
            actionTd,
            `<button type="button" class="btn btn-secondary btn-sm action-menu-item-danger" data-revoke-token="${token.id}" data-token-label="${escapeHtml(token.label)}">${bi("trash")} Revoke</button>`,
        );

        tr.appendChild(labelTd);
        tr.appendChild(grantsTd);
        tr.appendChild(usedTd);
        tr.appendChild(actionTd);
        listBody.appendChild(tr);
    });
}

async function loadApiTokensPage(domainsRes = null) {
    const card = document.getElementById("api-tokens-card");
    if (!card || !currentUser?.is_admin) return;

    const listBody = document.getElementById("api-tokens-list-tbody");
    if (!listBody) return;

    setTrustedHtml(
        listBody,
        '<tr><td colspan="4" style="text-align: center; color: var(--color-muted);">Loading API tokens...</td></tr>',
    );

    try {
        const domainsPromise = domainsRes ? Promise.resolve(domainsRes) : apiRequest("/api/domains");
        const [resolvedDomains, tokensRes] = await Promise.all([
            domainsPromise,
            apiRequest("/api/admin/api-tokens"),
        ]);

        if (!apiTokenDomainsChecklistReady) {
            renderApiTokenDomainsChecklist(resolvedDomains);
        }
        renderApiTokensTable(listBody, tokensRes);
    } catch (err) {
        setTrustedHtml(
            listBody,
            `<tr><td colspan="4" style="text-align: center; color: var(--danger);">Failed to load API tokens: ${escapeHtml(err.message)}</td></tr>`,
        );
    }
}

async function handleRevokeApiToken(tokenId, label) {
    const confirmed = await showConfirm({
        title: "Revoke API token",
        message: `Revoke token "${label}"? Scripts using it will stop working immediately.`,
        confirmLabel: "Revoke token",
        variant: "danger",
    });
    if (!confirmed) return;

    try {
        await apiRequest(`/api/admin/api-tokens/${tokenId}`, "DELETE");
        showAlert("success", `API token "${label}" revoked.`);
        document.getElementById("api-token-created-banner").style.display = "none";
        await loadApiTokensPage();
    } catch (err) {
        showAlert("error", err.message);
    }
}

document.getElementById("form-create-api-token")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const label = document.getElementById("api-token-label").value.trim();
    const isAdmin = !!document.getElementById("api-token-admin-cb")?.checked;
    const grants = collectApiTokenGrants();

    if (!label) return;
    if (!isAdmin && grants.length === 0) {
        showAlert("error", "Select at least one domain with permissions, or grant Admin access.");
        return;
    }
    if (!isAdmin && grants.some((grant) => grant.permissions.length === 0)) {
        showAlert("error", "Each selected domain needs at least one permission.");
        return;
    }

    const submitBtn = document.getElementById("btn-create-api-token");
    submitBtn.disabled = true;
    try {
        const payload = {
            label,
            is_admin: isAdmin,
            domains: isAdmin ? ["*"] : grants.map((grant) => grant.domain),
            grants: isAdmin ? [] : grants,
        };
        const result = await apiRequest("/api/admin/api-tokens", "POST", payload);
        showCreatedApiToken(result.data.token);
        showAlert("success", `API token "${label}" created. Copy it now — it will not be shown again.`);
        resetApiTokenForm();
        await loadApiTokensPage();
    } catch (err) {
        showAlert("error", err.message);
    } finally {
        submitBtn.disabled = false;
    }
});

document.getElementById("btn-copy-api-token")?.addEventListener("click", async () => {
    const value = document.getElementById("api-token-created-value")?.textContent || "";
    if (!value) return;
    try {
        await navigator.clipboard.writeText(value);
        showAlert("success", "API token copied to clipboard.");
    } catch {
        showAlert("error", "Could not copy automatically. Select and copy the token manually.");
    }
});

document.getElementById("api-tokens-list-tbody")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-revoke-token]");
    if (!button) return;
    handleRevokeApiToken(button.dataset.revokeToken, button.dataset.tokenLabel || "token");
});
