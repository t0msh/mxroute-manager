let dmarcModalDomain = "";

function bindDmarcCustomToggle(checkboxId, textareaId) {
    const checkbox = document.getElementById(checkboxId);
    const textarea = document.getElementById(textareaId);
    if (!checkbox || !textarea) return;
    const sync = () => {
        textarea.disabled = !checkbox.checked;
    };
    checkbox.addEventListener("change", sync);
    sync();
}

async function fetchDmarcPolicy(domain) {
    const result = await apiRequest(`/api/domains/${domain}/dmarc-policy`);
    if (!result.success || !result.data) {
        throw new Error(result.error?.message || "Failed to load DMARC policy");
    }
    return result.data;
}

async function saveDmarcPolicy(domain, { useCustom, value }) {
    const payload = {
        dmarc_record: useCustom ? value.trim() : null,
    };
    const result = await apiRequest(`/api/domains/${domain}/dmarc-policy`, "PATCH", payload);
    if (!result.success) {
        throw new Error(result.error?.message || "Failed to save DMARC policy");
    }
    return result.data;
}

function applyDmarcPolicyToSetupForm(policy) {
    const enabled = document.getElementById("setup-dmarc-custom-enabled");
    const value = document.getElementById("setup-dmarc-custom-value");
    if (!enabled || !value) return;
    enabled.checked = !!policy.custom;
    value.value = policy.custom ? (policy.custom_value || policy.effective || "") : (policy.default || "");
    value.disabled = !enabled.checked;
}

async function loadSetupDmarcPolicy() {
    if (!setupWizardDomain) return;
    try {
        const policy = await fetchDmarcPolicy(setupWizardDomain);
        applyDmarcPolicyToSetupForm(policy);
    } catch (err) {
        showAlert("error", err.message);
    }
}

async function persistSetupDmarcPolicyIfNeeded() {
    if (!setupWizardDomain) return;
    const enabled = document.getElementById("setup-dmarc-custom-enabled");
    const value = document.getElementById("setup-dmarc-custom-value");
    if (!enabled || !value) return;
    await saveDmarcPolicy(setupWizardDomain, {
        useCustom: enabled.checked,
        value: value.value,
    });
    invalidateApiCache(`/api/domains/${setupWizardDomain}/dmarc-policy`);
    invalidateApiCache(`/api/domains/${setupWizardDomain}/dns/setup-health`);
    invalidateApiCache(`/api/domains/${setupWizardDomain}/dns/health`);
}

function openDomainDmarcModal(domain) {
    dmarcModalDomain = domain;
    const label = document.getElementById("modal-dmarc-domain-label");
    const enabled = document.getElementById("modal-dmarc-custom-enabled");
    const value = document.getElementById("modal-dmarc-value");
    const defaultPreview = document.getElementById("modal-dmarc-default-preview");
    if (label) label.textContent = domain;
    if (enabled) enabled.checked = false;
    if (value) {
        value.value = "";
        value.disabled = true;
    }
    openModal("modal-domain-dmarc");

    fetchDmarcPolicy(domain)
        .then((policy) => {
            if (defaultPreview) defaultPreview.textContent = policy.default || "";
            if (enabled) enabled.checked = !!policy.custom;
            if (value) {
                value.value = policy.custom
                    ? (policy.custom_value || policy.effective || "")
                    : (policy.default || "");
                value.disabled = !enabled.checked;
            }
        })
        .catch((err) => showAlert("error", err.message));
}

async function handleDomainDmarcSave() {
    if (!dmarcModalDomain) return;
    const enabled = document.getElementById("modal-dmarc-custom-enabled");
    const value = document.getElementById("modal-dmarc-value");
    const btn = document.getElementById("btn-modal-dmarc-save");
    if (!enabled || !value) return;

    if (btn) btn.disabled = true;
    try {
        await saveDmarcPolicy(dmarcModalDomain, {
            useCustom: enabled.checked,
            value: value.value,
        });
        showAlert("success", `DMARC policy saved for ${dmarcModalDomain}.`);
        invalidateDomainCache(dmarcModalDomain);
        closeModal("modal-domain-dmarc");
        await loadDomainsList({ force: true });
    } catch (err) {
        showAlert("error", err.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

function initDomainDmarcUi() {
    bindDmarcCustomToggle("setup-dmarc-custom-enabled", "setup-dmarc-custom-value");
    bindDmarcCustomToggle("modal-dmarc-custom-enabled", "modal-dmarc-value");
    document.getElementById("btn-modal-dmarc-save")?.addEventListener("click", handleDomainDmarcSave);
}
