function renderNotificationTargets() {
    const container = document.getElementById("notification-targets-list");
    if (!container) return;
    if (!notificationTargets.length) {
        setTrustedHtml(container, '<p class="stat-card-subtitle" style="margin:0;">No targets configured yet.</p>');
        return;
    }
    setTrustedHtml(
        container,
        notificationTargets
            .map((target, index) => {
                const credNote = target.cred_env
                    ? `<div class="target-url">Token: <code>${escapeHtml(target.cred_env)}</code>${target.cred_env_configured ? "" : " (set in .env)"}</div>`
                    : "";
                return `
        <div class="notification-target-row" data-index="${index}">
            <div><strong>${escapeHtml(target.label || "Target")}</strong></div>
            <div>${escapeHtml(target.service || "")}</div>
            <div>
                <div class="target-url">${escapeHtml(target.url || "")}</div>
                ${credNote}
            </div>
            <div style="display:flex; gap:0.5rem;">
                <button type="button" class="btn btn-secondary btn-sm btn-edit-notification-target" data-index="${index}">Edit</button>
                <button type="button" class="btn btn-danger btn-sm btn-remove-notification-target" data-index="${index}">Remove</button>
            </div>
        </div>
    `;
            })
            .join("")
    );
}

function renderNotificationActionsGrid(selectedActions = []) {
    const container = document.getElementById("notification-actions-grid");
    if (!container) return;
    const selected = new Set(selectedActions);
    const parts = [];
    for (const group of notificationActionGroups) {
        parts.push(`<div class="notification-action-group-title">${escapeHtml(group.group)}</div>`);
        for (const action of group.actions) {
            const checked = selected.has(action.id) ? "checked" : "";
            parts.push(`
                <label class="notification-action-item">
                    <input type="checkbox" class="notification-action-checkbox" value="${escapeHtml(action.id)}" ${checked}>
                    <span>${escapeHtml(action.label)}</span>
                </label>
            `);
        }
    }
    setTrustedHtml(container, parts.join(""));
}

function getSelectedNotificationActions() {
    return Array.from(document.querySelectorAll(".notification-action-checkbox:checked"))
        .map((input) => input.value);
}

function setSelectedNotificationActions(actionIds) {
    const selected = new Set(actionIds || []);
    document.querySelectorAll(".notification-action-checkbox").forEach((input) => {
        input.checked = selected.has(input.value);
    });
}

function renderNotificationBuilderFields(serviceId, initialFields = {}) {
    const fieldsContainer = document.getElementById("notification-builder-fields");
    const service = notificationBuilderServices.find((item) => item.id === serviceId);
    const initial = initialFields || {};
    if (!fieldsContainer || !service) {
        if (fieldsContainer) setTrustedHtml(fieldsContainer, "");
        return;
    }
    setTrustedHtml(
        fieldsContainer,
        service.fields
            .map((field) => {
        if (field.id === "use_reset_smtp" && !notificationResetSmtpConfigured) {
            return `
                <div class="form-group mb-3">
                    <span style="font-size: 0.8rem; color: var(--color-secondary);">
                        Configure Mailbox Password Reset SMTP in Settings to enable shared SMTP for email notifications.
                    </span>
                </div>
            `;
        }
        const inputId = `notification-field-${field.id}`;
        const initialValue = initial[field.id];
        if (field.type === "select") {
            const options = (field.options || []).map((option) => {
                const defaultValue = initialValue !== undefined ? initialValue : (field.default || "");
                const selected = option === defaultValue ? "selected" : "";
                return `<option value="${escapeHtml(option)}" ${selected}>${escapeHtml(option)}</option>`;
            }).join("");
            return `
                <div class="form-group mb-3">
                    <label for="${inputId}">${escapeHtml(field.label)}</label>
                    <select id="${inputId}" data-field-id="${escapeHtml(field.id)}">${options}</select>
                </div>
            `;
        }
        if (field.type === "checkbox") {
            const checkedValue = initialValue !== undefined ? initialValue : field.default;
            const checked = checkedValue === true || checkedValue === "true" ? "checked" : "";
            return `
                <div class="form-group mb-3">
                    <label class="notification-action-item">
                        <input type="checkbox" id="${inputId}" data-field-id="${escapeHtml(field.id)}" ${checked}>
                        <span>${escapeHtml(field.label)}</span>
                    </label>
                </div>
            `;
        }
        const inputType = field.type === "secret" ? "password" : "text";
        const value = initialValue !== undefined && initialValue !== null ? String(initialValue) : "";
        return `
            <div class="form-group mb-3">
                <label for="${inputId}">${escapeHtml(field.label)}</label>
                <input type="${inputType}" id="${inputId}" data-field-id="${escapeHtml(field.id)}"
                    value="${escapeHtml(value)}"
                    placeholder="${escapeHtml(field.placeholder || "")}" ${field.required ? "required" : ""}>
            </div>
        `;
            })
            .join("")
    );
}

function collectNotificationBuilderFields() {
    const fields = {};
    document.querySelectorAll("#notification-builder-fields [data-field-id]").forEach((input) => {
        const key = input.getAttribute("data-field-id");
        if (input.type === "checkbox") {
            fields[key] = input.checked;
        } else {
            fields[key] = input.value.trim();
        }
    });
    return fields;
}

function showNotificationCompilePreview(result) {
    notificationCompiledResult = result;
    const preview = document.getElementById("notification-compile-preview");
    const urlPreview = document.getElementById("notification-compiled-url-preview");
    const envSnippet = document.getElementById("notification-env-snippet");
    const storeTokenRow = document.getElementById("notification-store-token-row");
    const serviceId = result.service || document.getElementById("notification-builder-service")?.value;
    const canStoreInEnv = Boolean(notificationCredEnvMap[serviceId]);
    if (!preview || !urlPreview) return;
    preview.style.display = "block";
    urlPreview.textContent = result.masked_url || result.url || "";
    if (storeTokenRow) {
        storeTokenRow.style.display = canStoreInEnv ? "block" : "none";
    }
    const restartHint = document.getElementById("notification-env-restart-hint");
    if (restartHint) {
        restartHint.style.display = canStoreInEnv ? "block" : "none";
    }
    const storeTokenEnv = document.getElementById("notification-store-token-env");
    if (storeTokenEnv) {
        storeTokenEnv.checked = Boolean(result.cred_env);
    }
    if (envSnippet) {
        envSnippet.value = result.env_snippet || "";
        envSnippet.style.display = "none";
    }
}

function resetNotificationTargetModal() {
    notificationCompiledResult = null;
    notificationEditIndex = null;
    const preview = document.getElementById("notification-compile-preview");
    if (preview) preview.style.display = "none";
    const labelInput = document.getElementById("notification-target-label");
    if (labelInput) labelInput.value = "";
    const pasteUrl = document.getElementById("notification-paste-url");
    if (pasteUrl) pasteUrl.value = "";
}

