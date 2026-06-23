
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

function formatDelegationDomainsHtml(item) {
    if (item.is_admin || item.domains.includes("*")) {
        return '<span style="color: var(--accent); font-weight: 600;">Admin</span>';
    }
    if (item.grants?.length) {
        return item.grants.map((grant) => {
            const labels = (grant.permissions || [])
                .map((perm) => DELEGATION_PERMISSION_LABELS[perm] || perm)
                .join(", ");
            return `<div><strong>${escapeHtml(grant.domain)}</strong><br><span style="color: var(--color-secondary); font-size: 0.8rem;">${escapeHtml(labels || "No permissions")}</span></div>`;
        }).join('<div style="margin-top: 0.5rem;"></div>');
    }
    if (item.domains.length > 0) {
        return item.domains.filter((d) => d !== "*").map(escapeHtml).join(", ");
    }
    return '<span style="color: var(--color-muted); font-style: italic;">None</span>';
}

function buildDelegationEmailCell(item) {
    const emailTd = document.createElement("td");
    const emailStrong = document.createElement("strong");
    emailStrong.textContent = item.email;
    emailTd.appendChild(emailStrong);
    if (!item.notification_email) return emailTd;

    const contactLine = document.createElement("div");
    contactLine.style.fontSize = "0.75rem";
    contactLine.style.color = "var(--color-secondary)";
    contactLine.style.marginTop = "0.25rem";
    contactLine.textContent = item.notification_email === item.email
        ? "Contact: email login"
        : `Contact: ${item.notification_email}`;
    emailTd.appendChild(contactLine);
    return emailTd;
}

function buildDelegationActionCell(item) {
    const actionTd = document.createElement("td");
    actionTd.style.textAlign = "right";
    const isSelf = currentUser && currentUser.email.toLowerCase() === item.email.toLowerCase();
    const isAdminGrant = item.is_admin || item.domains.includes("*");
    setTrustedHtml(actionTd, actionMenuHtml([
        {
            action: "edit",
            label: "Edit",
            icon: "gear",
            dataset: {
                email: item.email,
                grants: JSON.stringify(item.grants || []),
                "is-admin": isAdminGrant ? "1" : "0",
                "contact-email": item.contact_email || "",
            },
        },
        {
            action: "revoke",
            label: "Revoke",
            icon: "trash",
            danger: true,
            dataset: { email: item.email },
            disabled: isSelf,
            title: isSelf ? "You cannot revoke your own access." : "",
        },
    ]));
    return actionTd;
}

function appendDelegationRow(listBody, item) {
    knownDelegationUsers.add(item.email.toLowerCase());
    const tr = document.createElement("tr");
    tr.appendChild(buildDelegationEmailCell(item));

    const domainsTd = document.createElement("td");
    domainsTd.style.maxWidth = "360px";
    domainsTd.style.wordBreak = "break-word";
    setTrustedHtml(domainsTd, formatDelegationDomainsHtml(item));
    tr.appendChild(domainsTd);
    tr.appendChild(buildDelegationActionCell(item));
    listBody.appendChild(tr);
}

function renderDelegationDomainsChecklist(domainsRes, checklist) {
    if (!domainsRes.success || !domainsRes.data) return;

    setTrustedHtml(checklist, "");
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
        domainsRes.data.forEach((domain) => matrix.appendChild(createDelegationDomainRow(domain)));
    } else {
        setTrustedHtml(matrix, '<div style="color: var(--color-muted); font-size: 0.9rem;">No domains available yet.</div>');
    }
    checklist.appendChild(matrix);

    document.getElementById("delegation-admin-cb").addEventListener("change", (event) => {
        matrix.style.display = event.target.checked ? "none" : "flex";
    });
}

function renderDelegationsTable(listBody, delegationsRes) {
    setTrustedHtml(listBody, "");
    knownDelegationUsers = new Set();
    const rows = delegationsRes.success && delegationsRes.data ? delegationsRes.data : [];
    if (!rows.length) {
        setTrustedHtml(listBody, '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">No delegations configured yet.</td></tr>');
        return;
    }
    rows.forEach((item) => appendDelegationRow(listBody, item));
}

async function loadDelegationsPage(options = {}) {
    const listBody = document.getElementById("delegations-list-tbody");
    setTrustedHtml(listBody, '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">Querying access delegations...</td></tr>');

    const checklist = document.getElementById("delegation-domains-checklist");
    setTrustedHtml(checklist, '<div style="color: var(--color-muted); font-size: 0.9rem;">Loading available domains...</div>');

    try {
        const [domainsRes, delegationsRes] = await Promise.all([
            apiRequest("/api/domains"),
            apiRequest("/api/admin/delegations"),
        ]);

        if (delegationsRes?.permissions?.length) {
            delegationPermissionCatalog = delegationsRes.permissions;
        }
        renderDelegationDomainsChecklist(domainsRes, checklist);
        renderDelegationsTable(listBody, delegationsRes);
        updateDelegationPasswordHint();
    } catch (err) {
        setTrustedHtml(listBody, `<tr><td colspan="3" style="text-align: center; color: var(--danger);">Failed to load delegations: ${escapeHtml(err.message)}</td></tr>`);
        setTrustedHtml(checklist, `<div style="color: var(--danger); font-size: 0.9rem;">Failed to load domains: ${escapeHtml(err.message)}</div>`);
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

