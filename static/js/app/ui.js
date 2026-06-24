// Show Toast Alerts
let alertDismissTimer = null;
function showAlert(type, message) {
    const banner = document.getElementById("alert-banner");
    const icon = document.getElementById("alert-banner-icon");
    const text = document.getElementById("alert-banner-text");
    
    banner.className = `alert-banner ${type}`;
    const alertIcons = window.Mxm?.icons?.ALERT_ICONS ?? {};
    setTrustedHtml(icon, bi(alertIcons[type] || "bell"));
    text.textContent = message;
    
    banner.classList.add("show");
    
    if (alertDismissTimer) {
        clearTimeout(alertDismissTimer);
        alertDismissTimer = null;
    }
    if (type === "success" || type === "info") {
        alertDismissTimer = setTimeout(dismissAlert, 5000);
    }
}

function dismissAlert() {
    if (alertDismissTimer) {
        clearTimeout(alertDismissTimer);
        alertDismissTimer = null;
    }
    document.getElementById("alert-banner").classList.remove("show");
}

let _confirmResolver = null;
let _typedConfirmResolver = null;

function initConfirmModals() {
    const confirmModal = document.getElementById("modal-confirm");
    const typedModal = document.getElementById("modal-typed-confirm");
    const typedInput = document.getElementById("modal-typed-confirm-input");
    const typedSubmit = document.getElementById("modal-typed-confirm-submit");

    function closeConfirm(result) {
        confirmModal.classList.remove("show");
        if (_confirmResolver) {
            _confirmResolver(result);
            _confirmResolver = null;
        }
    }

    function closeTypedConfirm(result) {
        typedModal.classList.remove("show");
        typedInput.value = "";
        typedInput.classList.remove("matching");
        typedSubmit.disabled = true;
        if (_typedConfirmResolver) {
            _typedConfirmResolver(result);
            _typedConfirmResolver = null;
        }
    }

    document.getElementById("modal-confirm-submit").addEventListener("click", () => closeConfirm(true));
    document.getElementById("modal-confirm-cancel").addEventListener("click", () => closeConfirm(false));
    document.getElementById("modal-confirm-close").addEventListener("click", () => closeConfirm(false));

    document.getElementById("modal-typed-confirm-submit").addEventListener("click", () => {
        if (!typedSubmit.disabled) closeTypedConfirm(true);
    });
    document.getElementById("modal-typed-confirm-cancel").addEventListener("click", () => closeTypedConfirm(false));
    document.getElementById("modal-typed-confirm-close").addEventListener("click", () => closeTypedConfirm(false));

    typedInput.addEventListener("input", () => {
        const expected = typedInput.dataset.expected || "";
        const matches = typedInput.value.trim().toLowerCase() === expected.toLowerCase();
        typedSubmit.disabled = !matches;
        typedInput.classList.toggle("matching", matches);
    });

    typedInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !typedSubmit.disabled) {
            event.preventDefault();
            closeTypedConfirm(true);
        }
    });
}

function showConfirm({ title, message, confirmLabel = "Confirm", variant = "danger" }) {
    return new Promise((resolve) => {
        _confirmResolver = resolve;
        document.getElementById("modal-confirm-title").textContent = title;
        document.getElementById("modal-confirm-message").textContent = message;
        const submitBtn = document.getElementById("modal-confirm-submit");
        submitBtn.textContent = confirmLabel;
        submitBtn.className = variant === "danger" ? "btn btn-danger btn-sm" : "btn btn-primary btn-sm";
        document.getElementById("modal-confirm").classList.add("show");
    });
}

function showTypedConfirm({ title, message, expectedValue, confirmLabel = "Delete", inputLabel = "Type the email address to confirm" }) {
    return new Promise((resolve) => {
        _typedConfirmResolver = resolve;
        const input = document.getElementById("modal-typed-confirm-input");
        document.getElementById("modal-typed-confirm-title").textContent = title;
        document.getElementById("modal-typed-confirm-message").textContent = message;
        document.getElementById("modal-typed-confirm-label").textContent = inputLabel;
        document.getElementById("modal-typed-confirm-hint").textContent = `Enter exactly: ${expectedValue}`;
        document.getElementById("modal-typed-confirm-submit").textContent = confirmLabel;
        input.value = "";
        input.dataset.expected = expectedValue;
        input.classList.remove("matching");
        document.getElementById("modal-typed-confirm-submit").disabled = true;
        document.getElementById("modal-typed-confirm").classList.add("show");
        setTimeout(() => input.focus(), 100);
    });
}

// Copy to Clipboard Utility
async function copyText(elementId) {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    try {
        await navigator.clipboard.writeText(element.textContent || element.innerText);
        showAlert("success", "Copied to clipboard!");
    } catch (err) {
        showAlert("error", "Failed to copy text.");
    }
}

async function copyMailboxCredentials() {
    const setup = lastMailClientSetup;
    if (!setup?.email || !setup?.settings) {
        showAlert("warning", "No client settings to copy.");
        return;
    }

    try {
        await navigator.clipboard.writeText(formatMailboxCredentialsText(setup));
        showAlert("success", "Mail client settings copied to clipboard!");
    } catch (err) {
        showAlert("error", "Failed to copy settings.");
    }
}

function formatMailboxCredentialsText(setup) {
    return window.Mxm.utils.formatMailboxCredentialsText(setup);
}

function mailClientFieldHtml(prefix, key, label, value) {
    const id = `${prefix}-${key}`;
    return `
        <div class="mail-client-field">
            <span class="mail-client-label">${escapeHtml(label)}</span>
            <div class="copyable-code mail-client-value">
                <span id="${id}">${escapeHtml(value)}</span>
                <button type="button" class="btn btn-secondary btn-sm" onclick="copyText('${id}')">Copy</button>
            </div>
        </div>
    `;
}

function renderMailClientSetupBody(container, prefix, { email, password, settings }) {
    const parts = [];

    let accountHtml = mailClientFieldHtml(prefix, "email", "Email address", email);
    if (password) {
        accountHtml += mailClientFieldHtml(prefix, "password", "Password", password);
    } else {
        accountHtml += `<p class="mail-client-note">Password was set when the mailbox was created and cannot be retrieved here. Use <strong>Change password</strong> in Actions if needed.</p>`;
    }
    parts.push(`<div class="mail-client-section"><h4 class="mail-client-heading">Account</h4>${accountHtml}</div>`);

    parts.push(`
        <div class="mail-client-section">
            <h4 class="mail-client-heading">IMAP (incoming mail)</h4>
            ${mailClientFieldHtml(prefix, "imap-host", "Server", settings.imap.host)}
            ${mailClientFieldHtml(prefix, "imap-port", "Port", String(settings.imap.port))}
            ${mailClientFieldHtml(prefix, "imap-encryption", "Encryption", "SSL/TLS")}
        </div>
    `);

    parts.push(`
        <div class="mail-client-section">
            <h4 class="mail-client-heading">SMTP (outgoing mail)</h4>
            ${mailClientFieldHtml(prefix, "smtp-ssl-port", "Port (SSL/TLS)", String(settings.smtp_ssl.port))}
            ${mailClientFieldHtml(prefix, "smtp-starttls-port", "Port (STARTTLS)", String(settings.smtp_starttls.port))}
            ${mailClientFieldHtml(prefix, "smtp-host", "Server", settings.smtp_ssl.host)}
            <p class="mail-client-note">${escapeHtml(settings.username_note || "")}</p>
        </div>
    `);

    if (settings.webmail?.url) {
        let webmailNote = "";
        if (settings.webmail.status === "pending") {
            webmailNote = `<p class="mail-client-note">Webmail DNS is configured but may still be propagating.</p>`;
        }
        parts.push(`
            <div class="mail-client-section">
                <h4 class="mail-client-heading">Webmail</h4>
                ${mailClientFieldHtml(prefix, "webmail-url", "URL", settings.webmail.url)}
                ${webmailNote}
            </div>
        `);
    }

    setTrustedHtml(container, parts.join(""));
}

function showMailboxCredentials({ email, password, settings }) {
    lastMailClientSetup = { email, password, settings };
    const body = document.getElementById("mail-client-setup-body");
    const title = document.getElementById("mail-client-setup-title");
    if (title) {
        setTrustedHtml(title, `${bi("check-circle-fill")} Mailbox Created Successfully!`);
    }
    if (body) {
        renderMailClientSetupBody(body, "mail-client-card", { email, password, settings });
    }
    const card = document.getElementById("credentials-output-card");
    card.style.display = "block";
    card.scrollIntoView({ behavior: "smooth" });
}

async function openMailClientSetupModal(username) {
    const email = `${username}@${activeDomain}`;
    try {
        const result = await apiRequest(`/api/domains/${activeDomain}/mail-client-settings`);
        if (!result?.success || !result.data) {
            throw new Error("Could not load mail client settings.");
        }
        lastMailClientSetup = { email, settings: result.data };
        document.getElementById("modal-mail-client-setup-email").textContent = email;
        renderMailClientSetupBody(
            document.getElementById("modal-mail-client-setup-body"),
            "mail-client-modal",
            { email, settings: result.data },
        );
        openModal("modal-mail-client-setup");
    } catch (err) {
        showAlert("error", err.message || "Could not load mail client settings.");
    }
}

document.getElementById("btn-modal-copy-mail-client-setup")?.addEventListener("click", copyMailboxCredentials);

// Modal Toggle Helpers
function openModal(modalId) {
    document.getElementById(modalId).classList.add("show");
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove("show");
}

// Password Generator
function generateRandomPassword() {
    const length = 16;
    const charset = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+~`|}{[]:;?><,./-=";
    let retVal = "";
    
    retVal += "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[secureRandomInt(26)];
    retVal += "abcdefghijklmnopqrstuvwxyz"[secureRandomInt(26)];
    retVal += "0123456789"[secureRandomInt(10)];
    retVal += "!@#$%^&*()_+~`|}{[]:;?><,./-="[secureRandomInt(29)];
    
    for (let i = 4; i < length; ++i) {
        retVal += charset[secureRandomInt(charset.length)];
    }
    
    return shuffleString(retVal);
}

const requirements = {
    length: /.{8,}/,
    upper: /[A-Z]/,
    lower: /[a-z]/,
    number: /[0-9]/,
    special: /[^A-Za-z0-9]/
};

function setupPasswordValidation(inputId, listId, buttonId) {
    const input = document.getElementById(inputId);
    const list = document.getElementById(listId);
    const button = document.getElementById(buttonId);
    if (!input || !list || !button) return;

    input.addEventListener("input", () => {
        const val = input.value;
        let allValid = true;

        for (const [key, regex] of Object.entries(requirements)) {
            const el = list.querySelector(`[data-req="${key}"]`);
            if (el) {
                if (regex.test(val)) {
                    el.classList.add("valid");
                    window.Mxm?.icons?.setReqIcon(el, true);
                } else {
                    el.classList.remove("valid");
                    window.Mxm?.icons?.setReqIcon(el, false);
                    allValid = false;
                }
            }
        }
        button.disabled = !allValid;
    });
}

setupPasswordValidation("create-email-password", "create-email-requirements", "btn-provision-submit");
setupPasswordValidation("modal-pass-input", "modal-pass-requirements", "btn-modal-pass-submit");

function closeMobileSidebar() {
    document.body.classList.remove("sidebar-open");
    const toggle = document.getElementById("sidebar-toggle");
    const backdrop = document.getElementById("sidebar-backdrop");
    if (toggle) {
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "Open menu");
    }
    if (backdrop) backdrop.hidden = true;
}

function initMobileSidebar() {
    const toggle = document.getElementById("sidebar-toggle");
    const backdrop = document.getElementById("sidebar-backdrop");
    if (!toggle) return;

    toggle.addEventListener("click", () => {
        const open = !document.body.classList.contains("sidebar-open");
        document.body.classList.toggle("sidebar-open", open);
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
        if (backdrop) backdrop.hidden = !open;
    });

    backdrop?.addEventListener("click", closeMobileSidebar);
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeMobileSidebar();
    });
}

initMobileSidebar();

document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", () => {
        closeMobileSidebar();

        // Toggle Nav States
        document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
        item.classList.add("active");
        
        // Toggle Panel States
        const tab = item.getAttribute("data-tab");
        document.querySelectorAll(".tab-panel").forEach(panel => panel.classList.remove("active"));
        document.getElementById(`tab-${tab}`).classList.add("active");
        
        // Show/hide global domain selector (not needed on Domains, Access Control, or Settings pages)
        const domainSelector = document.getElementById("global-domain-selector");
        if (tab === "domains" || tab === "delegations" || tab === "settings" || tab === "logs" || tab === "notifications") {
            domainSelector.style.display = "none";
        } else {
            domainSelector.style.display = "";
        }
        
        const titleMap = {
            dashboard: { title: "Dashboard", subtitle: "Overview of your hosted mail accounts, resources, and endpoints." },
            domains: { title: "Domain Management", subtitle: "Register domains, verify DNS records, and configure redirection." },
            emails: { title: "Email Mailboxes", subtitle: "Provision new accounts, change quotas, and modify routing parameters." },
            forwarders: { title: "Email Forwarders", subtitle: "Create forwarders to redirect messages to external addresses." },
            spam: { title: "Spam & Whitelist Controls", subtitle: "Configure SpamAssassin thresholds and manage list records." },
            delegations: { title: "Access Control", subtitle: "Delegate email domain management rights to specific users." },
            logs: { title: "System Logs", subtitle: "View system actions, administrator operations, and authentication audits." },
            notifications: { title: "Notifications", subtitle: "Alert on audit events via ntfy, webhooks, email, and other Apprise-supported services." },
            settings: { title: "Settings", subtitle: "Configure global system parameters, authentication methods, and user interface options." }
        };
        
        const titleInfo = titleMap[tab];
        if (titleInfo) {
            document.getElementById("page-title").textContent = titleInfo.title;
            document.getElementById("page-subtitle").textContent = titleInfo.subtitle;
        }
        
        // Reload page specific data (uses cache when still fresh)
        if (!activeTabAllowedForDomain()) {
            showAlert("warning", "You do not have access to this section for the selected domain.");
            activateFirstAllowedTab();
            return;
        }
        triggerDataRefresh();
    });
});

