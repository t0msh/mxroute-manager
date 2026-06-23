function renderDnsCheckItem(key, check, { fixLabel = "Fix in Cloudflare" } = {}) {
    const statusClass = check.status === "pass" ? "pass" : check.status === "pending" ? "pending" : check.status === "skipped" ? "skipped" : check.status;
    const statusIcon = window.Mxm?.icons?.dnsStatusIcon(check.status) ?? "";
    const canFix = setupCfConfigured && (check.status === "warn" || check.status === "fail");
    const item = document.createElement("div");
    item.className = `dns-health-item ${statusClass}`;
    item.innerHTML = `
        <div class="dns-health-item-title">${statusIcon} ${escapeHtml(check.label)}</div>
        <div class="dns-health-item-message">${escapeHtml(check.message)}</div>
        ${canFix ? `<button class="btn btn-secondary btn-sm setup-fix-btn" data-record="${escapeHtml(key)}" style="margin-top: 0.6rem;">${escapeHtml(fixLabel)}</button>` : ""}
    `;
    return item;
}

function renderSetupDnsChecks(health) {
    const checksEl = document.getElementById("setup-dns-checks");
    if (!checksEl) return;
    setTrustedHtml(checksEl, "");
    setupCurrentHealth = health;

    Object.entries(health.checks || {}).forEach(([key, check]) => {
        if (key === "verification") return;
        checksEl.appendChild(renderDnsCheckItem(key, check));
    });

    checksEl.querySelectorAll(".setup-fix-btn").forEach(btn => {
        btn.addEventListener("click", () => handleFixDnsRecord(btn.dataset.record));
    });
}

function renderSetupVerifyCheck(health) {
    const el = document.getElementById("setup-verify-checks");
    if (!el) return;
    setTrustedHtml(el, "");
    const check = (health.checks || {}).verification;
    if (!check) {
        setTrustedHtml(el, `<div class="dns-health-item skipped"><div class="dns-health-item-message">Verification record is not available from MXroute yet.</div></div>`);
        return;
    }
    const item = renderDnsCheckItem("verification", check, { fixLabel: "Deploy verification TXT" });
    el.appendChild(item);
    const fixBtn = item.querySelector(".setup-fix-btn");
    if (fixBtn) fixBtn.addEventListener("click", () => handleFixDnsRecord("verification", { verify: true }));
}

async function fetchSetupHealth() {
    const result = await apiRequest(`/api/domains/${setupWizardDomain}/dns/setup-health`);
    if (!result.success || !result.data) {
        throw new Error(result.error?.message || "Health check failed");
    }
    if (result.data.cf_configured !== undefined) {
        setupCfConfigured = !!result.data.cf_configured;
        const cfMissing = document.getElementById("setup-cf-missing");
        if (cfMissing) cfMissing.style.display = setupCfConfigured ? "none" : "block";
    }
    return result.data;
}

async function loadSetupVerifyHealth() {
    if (!setupWizardDomain) return null;
    setSetupDomainLabel("setup-verify-domain-label");
    const el = document.getElementById("setup-verify-checks");
    if (el) setTrustedHtml(el, '<div style="color: var(--color-muted); padding: 1rem;">Checking domain verification...</div>');
    try {
        const health = await fetchSetupHealth();
        renderSetupVerifyCheck(health);
        return health;
    } catch (err) {
        if (el) setTrustedHtml(el, `<div class="dns-health-item fail"><div class="dns-health-item-message">${escapeHtml(err.message)}</div></div>`);
        showAlert("error", err.message);
        return null;
    }
}

async function loadSetupDnsHealth({ silent = false } = {}) {
    if (!setupWizardDomain) return null;
    setSetupDomainLabel("setup-step4-domain-label");
    const checksEl = document.getElementById("setup-dns-checks");
    if (checksEl && !silent) {
        setTrustedHtml(checksEl, '<div style="color: var(--color-muted); padding: 1rem;">Running DNS health check...</div>');
    }
    try {
        const health = await fetchSetupHealth();
        renderSetupDnsChecks(health);
        return health;
    } catch (err) {
        if (checksEl) {
            setTrustedHtml(checksEl, `<div class="dns-health-item fail"><div class="dns-health-item-message">${escapeHtml(err.message)}</div></div>`);
        }
        if (!silent) showAlert("error", err.message);
        return null;
    }
}

