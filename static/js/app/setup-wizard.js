// Auto-deploy verification TXT on entering Step 2, then show its status.
async function enterVerifyStep() {
    const health = await loadSetupVerifyHealth();
    const verify = health?.checks?.verification;
    if (health?.cf_configured && verify && verify.status !== "pass") {
        try {
            await apiRequest(`/api/domains/${setupWizardDomain}/dns/fix`, "POST", { records: ["verification"] });
            await loadSetupVerifyHealth();
        } catch (err) {
            showAlert("error", err.message);
        }
    }
}

async function enterMailDnsStep() {
    setSetupDomainLabel("setup-step4-domain-label");
    const wd = document.getElementById("setup-webmail-domain");
    if (wd) wd.textContent = setupWizardDomain;
    await loadSetupDmarcPolicy();
    await loadSetupDnsHealth();
}

function setupHealthComplete(health) {
    return !Object.values(health?.checks || {}).some(
        c => c.status === "warn" || c.status === "fail" || c.status === "pending"
    );
}

function stopSetupHealthPolling() {
    if (setupHealthPollTimer) {
        clearTimeout(setupHealthPollTimer);
        setupHealthPollTimer = null;
    }
}

// Poll setup-health every ~15s, live-updating the checklist, until everything
// passes or a ~3 minute deadline. Single in-flight request at a time.
function startSetupHealthPolling() {
    stopSetupHealthPolling();
    setupHealthPollDeadline = Date.now() + 180000;
    const tick = async () => {
        if (setupWizardStep !== 4) return;
        if (setupHealthPollInFlight) {
            setupHealthPollTimer = setTimeout(tick, 15000);
            return;
        }
        setupHealthPollInFlight = true;
        let health = null;
        try {
            health = await loadSetupDnsHealth({ silent: true });
        } finally {
            setupHealthPollInFlight = false;
        }
        if (setupWizardStep !== 4) return;
        if (health && setupHealthComplete(health)) {
            showAlert("success", `DNS for ${setupWizardDomain} is fully live.`);
            return;
        }
        if (Date.now() >= setupHealthPollDeadline) return;
        setupHealthPollTimer = setTimeout(tick, 15000);
    };
    setupHealthPollTimer = setTimeout(tick, 15000);
}

function showSetupDnsProgress(steps, isError = false) {
    const container = document.getElementById("setup-dns-progress");
    const list = document.getElementById("setup-dns-progress-list");
    if (!container || !list) return;
    container.style.display = "block";
    setTrustedHtml(list, "");
    (steps || []).forEach(step => {
        appendTrustedHtml(list, `<li>${bi("check-circle-fill")} ${escapeHtml(step)}</li>`);
    });
    if (isError) {
        appendTrustedHtml(list, `<li style="color: var(--danger);">${bi("x-circle-fill")} See alert for details</li>`);
    }
}

async function runSetupWizardDnsFix(records, options = {}) {
    const {
        verify = false,
        formatSuccess = (fixed) =>
            `Updated ${fixed.join(", ").toUpperCase()} in Cloudflare. DNS propagation may take a few minutes.`,
        emptyMessage = "Record already exists or was not applicable.",
        afterSuccess,
    } = options;
    const result = await apiRequest(
        `/api/domains/${setupWizardDomain}/dns/fix`,
        "POST",
        { records }
    );
    if (result.data?.steps) showSetupDnsProgress(result.data.steps);
    const fixed = result.data?.fixed || [];
    if (fixed.length > 0) {
        showAlert("success", formatSuccess(fixed));
    } else {
        showAlert("info", emptyMessage);
    }
    invalidateDomainCache(setupWizardDomain);
    await loadDomainsList({ force: true });
    if (verify) await loadSetupVerifyHealth();
    else await loadSetupDnsHealth();
    if (afterSuccess) await afterSuccess();
}

async function handleFixDnsRecord(recordType, { verify = false } = {}) {
    if (!setupWizardDomain) return;
    try {
        await runSetupWizardDnsFix([recordType], { verify });
    } catch (err) {
        if (err.steps) showSetupDnsProgress(err.steps, true);
        showAlert("error", err.message);
    }
}

async function handleSetupDeployAll() {
    if (!setupWizardDomain) return;
    const btn = document.getElementById("btn-setup-deploy-all");
    const records = ["mail", "mx", "spf", "dkim", "dmarc"];
    if (document.getElementById("setup-webmail-enabled")?.checked) records.push("webmail");
    if (btn) btn.disabled = true;
    try {
        await persistSetupDmarcPolicyIfNeeded();
        await runSetupWizardDnsFix(records, {
            formatSuccess: (fixed) =>
                `Deployed: ${fixed.join(", ").toUpperCase()}. DNS propagation may take a few minutes.`,
            emptyMessage: "All records already in place.",
            afterSuccess: async () => {
                startSetupHealthPolling();
            },
        });
    } catch (err) {
        if (err.steps) showSetupDnsProgress(err.steps, true);
        showAlert("error", err.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function updateSetupStep3State() {
    const statusEl = document.getElementById("setup-mxroute-status");
    const registerBtn = document.getElementById("btn-setup-register-mxroute");
    const nextBtn = document.getElementById("btn-setup-step3-next");

    setSetupDomainLabel("setup-register-domain-label");

    try {
        const result = await apiRequest(`/api/domains/${setupWizardDomain}/dns/setup-health`);
        const onMxroute = result.data?.on_mxroute;
        if (statusEl) {
            setTrustedHtml(
                statusEl,
                onMxroute
                    ? `<span class="status-indicator success"><span class="dot"></span> Registered on MXroute</span>`
                    : `<span class="status-indicator warning"><span class="dot"></span> Not yet registered on MXroute</span>`
            );
        }
        if (registerBtn) registerBtn.style.display = onMxroute ? "none" : "inline-flex";
        if (nextBtn) nextBtn.style.display = onMxroute ? "inline-flex" : "none";
    } catch (err) {
        if (statusEl) setTrustedHtml(statusEl, `<span style="color: var(--danger);">${escapeHtml(err.message)}</span>`);
    }
}

function isLikelyDomain(value) {
    return /^(?=.{1,253}$)([a-z0-9](-?[a-z0-9])*\.)+[a-z]{2,}$/i.test(value);
}

function initSetupWizard() {
    document.getElementById("btn-setup-step1-next")?.addEventListener("click", async () => {
        const domain = getSetupDomainValue();
        if (!domain || !isLikelyDomain(domain)) {
            showAlert("warning", "Please enter a valid domain name (e.g. example.com).");
            return;
        }
        setupWizardDomain = domain;
        setSetupWizardStep(2);
        await enterVerifyStep();
    });

    document.getElementById("btn-setup-verify-recheck")?.addEventListener("click", loadSetupVerifyHealth);

    document.getElementById("btn-setup-step2-back")?.addEventListener("click", () => setSetupWizardStep(1));
    document.getElementById("btn-setup-step2-next")?.addEventListener("click", async () => {
        setSetupWizardStep(3);
        await updateSetupStep3State();
    });

    document.getElementById("btn-setup-step3-back")?.addEventListener("click", async () => {
        setSetupWizardStep(2);
        await loadSetupVerifyHealth();
    });
    document.getElementById("btn-setup-step3-next")?.addEventListener("click", async () => {
        setSetupWizardStep(4);
        await enterMailDnsStep();
    });

    document.getElementById("btn-setup-recheck-dns")?.addEventListener("click", () => loadSetupDnsHealth());
    document.getElementById("btn-setup-deploy-all")?.addEventListener("click", handleSetupDeployAll);

    document.getElementById("btn-setup-step4-back")?.addEventListener("click", async () => {
        setSetupWizardStep(3);
        await updateSetupStep3State();
    });
    document.getElementById("btn-setup-step4-done")?.addEventListener("click", () => {
        stopSetupHealthPolling();
        showAlert("success", `Setup complete for ${setupWizardDomain}.`);
        const input = document.getElementById("setup-domain-input");
        if (input) input.value = "";
        setupWizardDomain = "";
        setSetupWizardStep(1);
    });

    document.getElementById("btn-setup-register-mxroute")?.addEventListener("click", async () => {
        const btn = document.getElementById("btn-setup-register-mxroute");
        if (btn) {
            btn.disabled = true;
            setTrustedHtml(btn, btnLabel("arrow-clockwise", "Registering...", true));
        }
        try {
            await apiRequest("/api/domains", "POST", { domain: setupWizardDomain });
            showAlert("success", `${setupWizardDomain} registered on MXroute. Continue to deploy mail DNS records.`);
            invalidateApiCache("/api/domains");
            await initDomainDropdowns();
            await loadDomainsList({ force: true });
            await updateSetupStep3State();
            const nextBtn = document.getElementById("btn-setup-step3-next");
            if (nextBtn) nextBtn.style.display = "inline-flex";
        } catch (err) {
            showAlert("error", err.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = "Register Domain on MXroute";
            }
        }
    });
}

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

