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
    setTrustedHtml(submitBtn, btnLabel("arrow-clockwise", "Provisioning...", true));
    
    try {
        const payload = {
            username,
            password,
            quota,
            limit
        };
        if (recoveryEmail) payload.recovery_email = recoveryEmail;

        await apiRequest(`/api/domains/${activeDomain}/email-accounts`, "POST", payload);

        const settingsResult = await apiRequest(
            `/api/domains/${activeDomain}/mail-client-settings`,
        );
        showMailboxCredentials({
            email: `${username}@${activeDomain}`,
            password,
            settings: settingsResult.data,
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

