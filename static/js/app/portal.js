function getSetupDomainValue() {
    return document.getElementById("setup-domain-input")?.value.trim().toLowerCase() || "";
}

function setSetupWizardStep(step) {
    setupWizardStep = step;
    document.querySelectorAll(".setup-wizard-step").forEach(el => {
        el.classList.toggle("active", parseInt(el.dataset.step, 10) === step);
        el.classList.toggle("completed", parseInt(el.dataset.step, 10) < step);
    });
    for (let i = 1; i <= 4; i++) {
        const panel = document.getElementById(`setup-step-${i}`);
        if (panel) panel.style.display = step === i ? "block" : "none";
    }
    if (step !== 4) stopSetupHealthPolling();
}

function setSetupDomainLabel(id) {
    const el = document.getElementById(id);
    if (el) setTrustedHtml(el, `<strong>Domain:</strong> ${escapeHtml(setupWizardDomain)}`);
}

let resetPortalDomain = "";
let resetPortalLoadedPrefix = "";
let resetPortalSelectedTheme = "emerald";
let resetPortalDeployConfigured = false;

function highlightResetPortalTheme(themeId) {
    const theme = themeId || "emerald";
    resetPortalSelectedTheme = theme;
    document.querySelectorAll(".portal-theme-card[data-portal-theme]").forEach(card => {
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
    setTrustedHtml(select, '<option value="">Loading domains...</option>');
    try {
        const result = await cachedFetch("/api/domains");
        setTrustedHtml(select, '<option value="">Select a domain...</option>');
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
            setTrustedHtml(select, '<option value="">No domains on MXroute yet</option>');
        }
    } catch {
        setTrustedHtml(select, '<option value="">Error loading domains</option>');
    }
}

function updateResetPortalUrlPreview() {
    const preview = document.getElementById("reset-portal-url-preview");
    const prefixInput = document.getElementById("reset-portal-prefix");
    const senderDomain = document.getElementById("reset-portal-sender-domain");
    if (!preview || !prefixInput) return;
    const prefix = prefixInput.value.trim().toLowerCase() || "reset";
    const domain = resetPortalDomain || "example.com";
    preview.textContent = publicOriginHost(`${prefix}.${domain}`);
    if (senderDomain) senderDomain.textContent = domain;
}

function getResetPortalFormValues() {
    return {
        enabled: document.getElementById("reset-portal-enabled")?.checked ?? false,
        subdomain_prefix: document.getElementById("reset-portal-prefix")?.value.trim().toLowerCase() || "",
        portal_title: document.getElementById("reset-portal-title")?.value.trim() || "",
        portal_theme: resetPortalSelectedTheme,
    };
}

function updateResetPortalSubmitButton() {
    const btn = document.getElementById("btn-reset-portal-save");
    if (!btn || btn.disabled) return;
    const { enabled } = getResetPortalFormValues();
    if (!enabled) {
        btn.textContent = "Save";
        return;
    }
    btn.textContent = resetPortalDeployConfigured ? "Deploy Portal" : "Save Portal Settings";
}

async function uploadResetPortalLogoFile(file) {
    if (!resetPortalDomain || !file) return null;
    const formData = new FormData();
    formData.append("logo", file);
    bumpApiActivity(1);
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
        return result.data;
    } finally {
        bumpApiActivity(-1);
    }
}

async function deployResetPortalDns() {
    const controller = new AbortController();
    const deployTimeout = window.setTimeout(() => controller.abort(), 180000);
    bumpApiActivity(1);
    try {
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
        const result = await parseJsonResponse(response);
        if (!response.ok || !result.success) {
            throw new Error(result.error?.message || "Deploy failed.");
        }
        return result.data;
    } catch (err) {
        if (err.name === "AbortError") {
            throw new Error("Deploy timed out after 3 minutes. Check reverse proxy settings and try again.");
        }
        throw err;
    } finally {
        window.clearTimeout(deployTimeout);
        bumpApiActivity(-1);
    }
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
    const manualSnippets = document.getElementById("reset-portal-manual-snippets");

    resetPortalDeployConfigured = !!data.deploy_configured;

    if (deployMissing) {
        const missing = data.deploy_missing || [];
        deployMissing.style.display = missing.length ? "block" : "none";
        const list = document.getElementById("reset-portal-deploy-missing-list");
        if (list) list.textContent = missing.join(", ");
    }

    if (manualSnippets) {
        const snippets = data.manual_snippets;
        const isManual = data.proxy_backend === "manual";
        manualSnippets.style.display = isManual && snippets ? "block" : "none";
        if (isManual && snippets) {
            const originEl = document.getElementById("reset-portal-manual-origin");
            if (originEl) originEl.textContent = snippets.origin || "";
            const setSnippet = (id, key) => {
                const el = document.getElementById(id);
                if (el) el.textContent = snippets[key] || "";
            };
            setSnippet("reset-portal-snippet-nginx", "nginx");
            setSnippet("reset-portal-snippet-caddy", "caddy");
            setSnippet("reset-portal-snippet-haproxy", "haproxy");
            setSnippet("reset-portal-snippet-apache", "apache");
        }
    }
    updateResetPortalSubmitButton();

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
        setTrustedHtml(httpsStatus, linkifyMessageUrl(data.https.message || "", httpsUrl));
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

async function saveResetPortalSettings() {
    if (!resetPortalDomain) {
        showAlert("warning", "Select a domain first.");
        return;
    }
    const { enabled, subdomain_prefix, portal_title, portal_theme } = getResetPortalFormValues();
    if (enabled && !subdomain_prefix) {
        showAlert("warning", "Subdomain prefix is required when the portal is enabled.");
        return;
    }

    const btn = document.getElementById("btn-reset-portal-save");
    const loadingLabel = enabled && resetPortalDeployConfigured ? "Deploying..." : "Saving...";
    setBtnLoading(btn, true, { icon: "rocket-takeoff", text: loadingLabel });

    try {
        const pendingLogo = document.getElementById("reset-portal-logo")?.files?.[0];
        if (pendingLogo) {
            await uploadResetPortalLogoFile(pendingLogo);
            const logoInput = document.getElementById("reset-portal-logo");
            if (logoInput) logoInput.value = "";
        }

        const result = await apiRequest(
            `/api/domains/${resetPortalDomain}/reset-portal`,
            "PATCH",
            { enabled, subdomain_prefix, portal_title, portal_theme }
        );

        const portalData = result.data;
        if (enabled && resetPortalDeployConfigured) {
            setBtnLoading(btn, true, { icon: "rocket-takeoff", text: "Deploying..." });
            const deployResult = await deployResetPortalDns();
            const https = deployResult?.https;
            if (https?.status === "pass") {
                showAlert("success", "Reset portal deployed and HTTPS is live.");
            } else {
                showAlert(
                    "success",
                    "Portal settings saved. DNS and reverse proxy configured — HTTPS may take a few minutes to become live."
                );
            }
            await loadResetPortalSettings(resetPortalDomain);
            return;
        }

        showAlert("success", enabled ? "Reset portal settings saved." : "Reset portal disabled.");
        if (portalData?.teardown_steps?.length) {
            showAlert("info", portalData.teardown_steps.join(" · "));
        }
        renderResetPortalForm(portalData);
    } catch (err) {
        showAlert("error", err.message);
    } finally {
        setBtnLoading(btn, false);
        updateResetPortalSubmitButton();
    }
}

function bindResetPortalPrefixInput() {
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
}

function bindResetPortalLogoHandlers() {
    document.getElementById("reset-portal-logo")?.addEventListener("change", async (event) => {
        if (!resetPortalDomain) return;
        const file = event.target.files?.[0];
        if (!file) return;
        try {
            const data = await uploadResetPortalLogoFile(file);
            showAlert("success", "Logo uploaded.");
            renderResetPortalForm(data);
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
}

function initResetPortal() {
    const select = document.getElementById("reset-portal-domain-select");
    if (!select) return;

    populateResetPortalDomainSelect();

    select.addEventListener("change", () => {
        loadResetPortalSettings(select.value);
    });

    bindResetPortalPrefixInput();
    document.getElementById("reset-portal-enabled")?.addEventListener("change", updateResetPortalSubmitButton);

    document.querySelectorAll(".portal-theme-card[data-portal-theme]").forEach(card => {
        card.addEventListener("click", () => {
            highlightResetPortalTheme(card.getAttribute("data-portal-theme"));
        });
    });

    document.getElementById("btn-reset-portal-save")?.addEventListener("click", saveResetPortalSettings);
    bindResetPortalLogoHandlers();
}

