// --- 1. Global App State & Helpers ---
let activeDomain = "";
let activeDomainMailHosting = null;
let accountQuota = null;
let currentUser = null;

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function jsString(value) {
    return JSON.stringify(String(value ?? ""));
}

function secureRandomInt(max) {
    const buffer = new Uint32Array(1);
    crypto.getRandomValues(buffer);
    return buffer[0] % max;
}

function shuffleString(str) {
    const chars = str.split("");
    for (let i = chars.length - 1; i > 0; i--) {
        const j = secureRandomInt(i + 1);
        [chars[i], chars[j]] = [chars[j], chars[i]];
    }
    return chars.join("");
}

// Helper to get cookie by name
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return "";
}

// Helper to make API requests easily
async function apiRequest(url, method = "GET", body = null) {
    const options = {
        method,
        headers: {
            "Content-Type": "application/json"
        }
    };
    if (body) {
        options.body = JSON.stringify(body);
    }

    if (method !== "GET") {
        const csrfToken = getCookie("csrf_token");
        if (csrfToken) {
            options.headers["X-CSRF-Token"] = csrfToken;
        }
    }
    
    try {
        const response = await fetch(url, options);
        let result;
        try {
            result = await response.json();
        } catch (e) {
            result = { success: response.ok };
        }
        
        if (!response.ok) {
            const errMsg = result.error ? result.error.message : `HTTP Error ${response.status}`;
            throw new Error(errMsg);
        }
        return result;
    } catch (err) {
        console.error(`API Request failed on ${url}:`, err);
        throw err;
    }
}

// Show Toast Alerts
function showAlert(type, message) {
    const banner = document.getElementById("alert-banner");
    const icon = document.getElementById("alert-banner-icon");
    const text = document.getElementById("alert-banner-text");
    
    banner.className = `alert-banner ${type}`;
    const icons = { success: "✅", error: "❌", warning: "⚠️", info: "ℹ️" };
    icon.textContent = icons[type] || "🔔";
    text.textContent = message;
    
    banner.classList.add("show");
    
    if (type === "success" || type === "info") {
        setTimeout(dismissAlert, 5000);
    }
}

function dismissAlert() {
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

// --- 2. Live Password Verification Logic ---
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
                    el.innerHTML = `✔ ${el.textContent.slice(2)}`;
                } else {
                    el.classList.remove("valid");
                    el.innerHTML = `✖ ${el.textContent.slice(2)}`;
                    allValid = false;
                }
            }
        }
        button.disabled = !allValid;
    });
}

// Initialize Password Validations
setupPasswordValidation("create-email-password", "create-email-requirements", "btn-provision-submit");
setupPasswordValidation("modal-pass-input", "modal-pass-requirements", "btn-modal-pass-submit");


// --- 3. Tab Navigation Controller ---
document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", () => {
        // Toggle Nav States
        document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
        item.classList.add("active");
        
        // Toggle Panel States
        const tab = item.getAttribute("data-tab");
        document.querySelectorAll(".tab-panel").forEach(panel => panel.classList.remove("active"));
        document.getElementById(`tab-${tab}`).classList.add("active");
        
        // Show/hide global domain selector (not needed on Domains, Access Control, or Settings pages)
        const domainSelector = document.getElementById("global-domain-selector");
        if (tab === "domains" || tab === "delegations" || tab === "settings") {
            domainSelector.style.display = "none";
        } else {
            domainSelector.style.display = "";
        }
        
        // Update Title & Page details
        const titleMap = {
            dashboard: { title: "Dashboard", subtitle: "Overview of your hosted mail accounts, resources, and endpoints." },
            domains: { title: "Domain Management", subtitle: "Register domains, verify DNS records, and configure redirection." },
            emails: { title: "Email Mailboxes", subtitle: "Provision new accounts, change quotas, and modify routing parameters." },
            forwarders: { title: "Email Forwarders", subtitle: "Create forwarders to redirect messages to external addresses." },
            spam: { title: "Spam & Whitelist Controls", subtitle: "Configure SpamAssassin thresholds and manage list records." },
            delegations: { title: "Access Control", subtitle: "Delegate email domain management rights to specific users." },
            settings: { title: "Settings", subtitle: "Configure global system parameters, authentication methods, and user interface options." }
        };
        
        document.getElementById("page-title").textContent = titleMap[tab].title;
        document.getElementById("page-subtitle").textContent = titleMap[tab].subtitle;
        
        // Reload page specific data
        triggerDataRefresh();
    });
});


// --- 4. Main Data Refresher ---
async function triggerDataRefresh() {
    const activeTab = document.querySelector(".nav-item.active").getAttribute("data-tab");
    if (!activeDomain && activeTab !== "delegations" && activeTab !== "domains" && activeTab !== "settings") return;
    
    try {
        switch (activeTab) {
            case "dashboard":
                await Promise.all([
                    loadAccountQuota(),
                    loadDomainDetails(activeDomain),
                    loadDNSInfo(activeDomain),
                    loadDnsHealth(activeDomain)
                ]);
                break;
            case "domains":
                await loadDomainsList();
                break;
            case "emails":
                // Set domain display labels
                document.getElementById("create-email-domain-display").textContent = `@${activeDomain}`;
                await Promise.all([
                    loadEmailsList(activeDomain),
                    checkDomainMailHostingStatus(activeDomain)
                ]);
                break;
            case "forwarders":
                document.getElementById("forwarder-domain-display").textContent = `@${activeDomain}`;
                await Promise.all([
                    loadForwardersList(activeDomain),
                    loadCatchAll(activeDomain),
                    loadPointersList(activeDomain),
                    checkDomainMailHostingStatus(activeDomain)
                ]);
                break;
            case "spam":
                await Promise.all([
                    loadSpamSettings(activeDomain),
                    checkDomainMailHostingStatus(activeDomain)
                ]);
                break;
            case "delegations":
                await loadDelegationsPage();
                break;
            case "settings":
                await loadSettingsPage();
                break;
        }
    } catch (err) {
        showAlert("error", err.message);
    }
}

// Global Refresh Actions
document.getElementById("btn-refresh-data").addEventListener("click", async () => {
    const refreshBtn = document.getElementById("btn-refresh-data");
    refreshBtn.textContent = "⌛ Refreshing...";
    refreshBtn.disabled = true;
    try {
        await triggerDataRefresh();
        showAlert("success", "Data refreshed successfully.");
    } catch (e) {
        showAlert("error", "Refresh failed: " + e.message);
    } finally {
        refreshBtn.innerHTML = "🔄 Refresh Data";
        refreshBtn.disabled = false;
    }
});


// --- 5. Specific Feature Functions ---

// 5.1 Storage Quotas
async function loadAccountQuota() {
    if (currentUser && !currentUser.is_admin) return;
    try {
        const result = await apiRequest("/api/quota");
        if (result && result.success && result.data) {
            const data = result.data;
            accountQuota = data;
            const limitGB = data.total_limit === 0 ? "Unlimited" : (data.total_limit / (1024 ** 3)).toFixed(1) + " GB";
            const usedGB = (data.total_used / (1024 ** 3)).toFixed(2) + " GB";
            const percent = data.percent_used.toFixed(1) + "%";
            
            // Update Sidebar
            document.getElementById("sidebar-quota-text").textContent = `${usedGB} / ${limitGB}`;
            const bar = document.getElementById("sidebar-quota-bar");
            bar.style.width = percent;
            bar.className = "quota-bar-fill";
            if (data.percent_used > 80) bar.classList.add("warning");
            if (data.percent_used > 95) bar.classList.add("danger");
            
            // Update Dashboard panel
            document.getElementById("quota-used").textContent = usedGB;
            document.getElementById("quota-limit").textContent = limitGB;
            document.getElementById("quota-percentage").textContent = percent;
            
            if (data.grace_period) {
                document.getElementById("quota-grace").innerHTML = `<span style="color: var(--danger);">Quota Exceeded! Deadline: ${escapeHtml(data.grace_period.deadline)}</span>`;
            } else {
                document.getElementById("quota-grace").textContent = "Compliant";
            }
        }
    } catch (err) {
        console.warn("Could not load account quotas:", err);
    }
}

// 5.2 Domains List
async function loadDomainsList() {
    const tbody = document.getElementById("domains-list-tbody");
    tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">Querying domains...</td></tr>';
    
    try {
        const result = await apiRequest("/api/domains");
        tbody.innerHTML = "";
        
        if (result.success && result.data && result.data.length > 0) {
            // Render rows immediately with a loading spinner in the status column
            const rows = {};
            result.data.forEach(domain => {
                const tr = document.createElement("tr");
                const statusId = `domain-status-${domain.replace(/[^a-zA-Z0-9-]/g, '-')}`;
                tr.innerHTML = `
                    <td><strong>${escapeHtml(domain)}</strong></td>
                    <td id="${statusId}"><span style="color: var(--color-muted); font-size: 0.85rem;">⌛ checking...</span></td>
                    <td style="text-align: right;">
                        <button class="btn btn-danger btn-sm" onclick="handleDeleteDomain(${jsString(domain)})">Delete</button>
                    </td>
                `;
                tbody.appendChild(tr);
                rows[domain] = statusId;
            });

            // Fetch each domain's details in parallel and update status badges as results arrive
            await Promise.allSettled(result.data.map(async domain => {
                const statusId = rows[domain];
                const cell = document.getElementById(statusId);
                if (!cell) return;
                try {
                    const details = await apiRequest(`/api/domains/${domain}`);
                    if (details.success && details.data) {
                        const mailOn = details.data.mail_hosting;
                        cell.innerHTML = mailOn
                            ? `<span class="status-indicator success"><span class="dot"></span> Mail Enabled</span>`
                            : `<span class="status-indicator danger"><span class="dot"></span> Mail Disabled</span>`;
                    } else {
                        cell.innerHTML = `<span style="color: var(--color-muted); font-size: 0.85rem;">Unknown</span>`;
                    }
                } catch {
                    cell.innerHTML = `<span style="color: var(--color-muted); font-size: 0.85rem;">Unknown</span>`;
                }
            }));
        } else {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">No domains found on this account.</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--danger); font-weight: 500;">Failed to load domains: ${escapeHtml(err.message)}</td></tr>`;
    }
}

// 5.3 Domain Details (Dashboard Overview)
async function loadDomainDetails(domain) {
    try {
        const result = await apiRequest(`/api/domains/${domain}`);
        if (result.success && result.data) {
            const data = result.data;
            activeDomainMailHosting = !!data.mail_hosting;
            document.getElementById("dash-mail-status").innerHTML = data.mail_hosting ?
                `<span class="status-indicator success"><span class="dot"></span> Enabled</span>` :
                `<span class="status-indicator danger"><span class="dot"></span> Disabled</span>`;
            
            document.getElementById("dash-pointers-count").textContent = data.pointers ? data.pointers.length : 0;
        }
        
        // Fetch mailboxes count
        const mailboxRes = await apiRequest(`/api/domains/${domain}/email-accounts`);
        if (mailboxRes.success && mailboxRes.data) {
            document.getElementById("dash-mailboxes-count").textContent = mailboxRes.data.length;
        } else {
            document.getElementById("dash-mailboxes-count").textContent = 0;
        }
    } catch (err) {
        console.warn("Could not load domain details:", err);
    }
}

// Toggle Mail Hosting status
document.getElementById("btn-toggle-mail-hosting").addEventListener("click", async () => {
    if (!activeDomain || activeDomainMailHosting === null) return;
    const nextState = !activeDomainMailHosting;
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/mail-status`, "PATCH", { enabled: nextState });
        showAlert("success", `Mail hosting status updated successfully.`);
        await loadDomainDetails(activeDomain);
    } catch (err) {
        showAlert("error", err.message);
    }
});

// Domain Verification Key
document.getElementById("btn-fetch-verify-key").addEventListener("click", async () => {
    const display = document.getElementById("verify-key-display");
    const nameEl = document.getElementById("verify-dns-name");
    const valEl = document.getElementById("verify-dns-value");
    
    try {
        const result = await apiRequest("/api/verification-key");
        if (result.success && result.data) {
            nameEl.textContent = result.data.record.name;
            valEl.textContent = result.data.record.value;
            display.style.display = "block";
            showAlert("success", "Verification key retrieved.");
        }
    } catch (err) {
        showAlert("error", err.message);
    }
});

// Create Domain
document.getElementById("form-create-domain").addEventListener("submit", async (e) => {
    e.preventDefault();
    const domainInput = document.getElementById("new-domain-name");
    const domainName = domainInput.value.trim().toLowerCase();
    if (!domainName) return;
    
    const isCfAuto = document.getElementById("chk-cf-auto") && document.getElementById("chk-cf-auto").checked;
    const submitBtn = document.getElementById("btn-create-domain-submit");
    const progressContainer = document.getElementById("cf-progress-container");
    const progressList = document.getElementById("cf-progress-list");
    
    submitBtn.disabled = true;
    
    if (isCfAuto) {
        submitBtn.textContent = "⌛ Deploying DNS...";
        progressContainer.style.display = "block";
        progressList.innerHTML = '<li>⌛ Initializing setup flow...</li>';
        
        try {
            const result = await apiRequest("/api/cloudflare/setup", "POST", { domain: domainName });
            progressList.innerHTML = "";
            if (result.steps) {
                result.steps.forEach(step => {
                    progressList.innerHTML += `<li>✅ ${escapeHtml(step)}</li>`;
                });
            }
            showAlert("success", `Domain "${domainName}" set up successfully in Cloudflare and MXroute!`);
            domainInput.value = "";
            document.getElementById("chk-cf-auto").checked = false;
            await loadDomainsList();
            await initDomainDropdowns();
        } catch (err) {
            if (err.steps) {
                progressList.innerHTML = "";
                err.steps.forEach(step => {
                    progressList.innerHTML += `<li>✅ ${escapeHtml(step)}</li>`;
                });
            }
            progressList.innerHTML += `<li style="color: var(--danger);">❌ Failed: ${escapeHtml(err.message)}</li>`;
            showAlert("error", `Setup failed: ${err.message}`);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = "Create Domain Record";
        }
    } else {
        submitBtn.textContent = "⌛ Registering...";
        try {
            await apiRequest("/api/domains", "POST", { domain: domainName });
            showAlert("success", `Domain "${domainName}" added successfully!`);
            domainInput.value = "";
            progressContainer.style.display = "none";
            await loadDomainsList();
            await initDomainDropdowns(); // Refresh active selectors
        } catch (err) {
            showAlert("error", err.message);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = "Create Domain Record";
        }
    }
});

// Delete Domain
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
        await loadDomainsList();
        await initDomainDropdowns();
    } catch (err) {
        showAlert("error", err.message);
    }
}

// 5.4 Domain Pointers
async function loadPointersList(domain) {
    const tbody = document.getElementById("pointers-tbody");
    tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">Loading pointers...</td></tr>';
    
    try {
        const result = await apiRequest(`/api/domains/${domain}/pointers`);
        tbody.innerHTML = "";
        
        if (result.success && result.data && result.data.length > 0) {
            result.data.forEach(pointer => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td><strong>${escapeHtml(pointer.pointer)}</strong></td>
                    <td><span class="badge" style="font-size:0.75rem; padding:0.1rem 0.4rem; background:rgba(255,255,255,0.05); border: 1px solid var(--glass-border); border-radius:4px;">${escapeHtml(pointer.type)}</span></td>
                    <td style="text-align: right;">
                        <button class="btn btn-danger btn-sm btn-icon" onclick="handleDeletePointer(${jsString(pointer.pointer)})">×</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">No pointers configured</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--danger);">Failed to load pointers</td></tr>`;
    }
}

// Add Pointer Modal Open
document.getElementById("btn-open-pointer-modal").addEventListener("click", () => {
    document.getElementById("pointer-name-input").value = "";
    openModal("modal-add-pointer");
});

// Create Pointer Form Submit
document.getElementById("form-modal-create-pointer").addEventListener("submit", async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById("pointer-name-input");
    const typeSelect = document.getElementById("pointer-type-select");
    const pointer = nameInput.value.trim();
    const alias = typeSelect.value === "alias";
    
    if (!pointer) return;
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/pointers`, "POST", { pointer, alias });
        showAlert("success", `Pointer "${pointer}" created successfully.`);
        closeModal("modal-add-pointer");
        await loadPointersList(activeDomain);
        await loadDomainDetails(activeDomain);
    } catch (err) {
        showAlert("error", err.message);
    }
});

// Delete Pointer
async function handleDeletePointer(pointer) {
    const confirmed = await showConfirm({
        title: "Remove Pointer",
        message: `Remove pointer "${pointer}" from ${activeDomain}?`,
        confirmLabel: "Remove Pointer"
    });
    if (!confirmed) return;
    try {
        await apiRequest(`/api/domains/${activeDomain}/pointers/${pointer}`, "DELETE");
        showAlert("success", "Pointer deleted.");
        await loadPointersList(activeDomain);
        await loadDomainDetails(activeDomain);
    } catch (err) {
        showAlert("error", err.message);
    }
}

// 5.5 Catch-All Settings
async function loadCatchAll(domain) {
    const typeSelect = document.getElementById("catch-all-type");
    const addressGroup = document.getElementById("catch-all-address-group");
    const addressInput = document.getElementById("catch-all-address");
    
    try {
        const result = await apiRequest(`/api/domains/${domain}/catch-all`);
        if (result.success && result.data) {
            typeSelect.value = result.data.type;
            if (result.data.type === "address") {
                addressGroup.style.display = "block";
                addressInput.value = result.data.address || "";
            } else {
                addressGroup.style.display = "none";
                addressInput.value = "";
            }
        }
    } catch (err) {
        console.warn("Could not load catch-all configuration:", err);
    }
}

// Catch-All Type Visibility Toggle
document.getElementById("catch-all-type").addEventListener("change", (e) => {
    const group = document.getElementById("catch-all-address-group");
    if (e.target.value === "address") {
        group.style.display = "block";
    } else {
        group.style.display = "none";
    }
});

// Catch-All Update Submit
document.getElementById("form-catch-all").addEventListener("submit", async (e) => {
    e.preventDefault();
    const type = document.getElementById("catch-all-type").value;
    const address = document.getElementById("catch-all-address").value.trim();
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/catch-all`, "PATCH", { type, address: type === "address" ? address : null });
        showAlert("success", "Catch-All configuration updated.");
    } catch (err) {
        showAlert("error", err.message);
    }
});

// 5.6 DNS Configuration Info
async function loadDNSInfo(domain) {
    const mxContainer = document.getElementById("dns-mx-container");
    const spfEl = document.getElementById("dns-spf");
    const dkimEl = document.getElementById("dns-dkim");
    
    try {
        const result = await apiRequest(`/api/domains/${domain}/dns`);
        if (result.success && result.data) {
            const data = result.data;
            
            // Format MX Records
            if (data.mx_records && data.mx_records.length > 0) {
                mxContainer.innerHTML = "";
                data.mx_records.forEach((mx, index) => {
                    const rowId = `mx-rec-${index}`;
                    const mxRow = document.createElement("div");
                    mxRow.className = "copyable-code mb-2";
                    mxRow.innerHTML = `
                        <span><strong>Priority ${escapeHtml(mx.priority)}:</strong> <span id="${rowId}">${escapeHtml(mx.hostname)}</span></span>
                        <button class="copy-btn" onclick="copyText('${rowId}')">Copy</button>
                    `;
                    mxContainer.appendChild(mxRow);
                });
            } else {
                mxContainer.innerHTML = `<div style="color: var(--color-muted);">No MX records reported by API.</div>`;
            }
            
            // SPF
            spfEl.textContent = data.spf ? data.spf.value : "v=spf1 include:mxroute.com -all";
            
            // DKIM
            dkimEl.textContent = data.dkim ? data.dkim.value : "No DKIM key available";

            // DMARC
            const dmarcEl = document.getElementById("dns-dmarc");
            if (dmarcEl) {
                dmarcEl.textContent = data.dmarc ? data.dmarc.value : "v=DMARC1; p=none; sp=none; adkim=r; aspf=r;";
            }
        }
    } catch (err) {
        mxContainer.innerHTML = `<div style="color: var(--danger);">Failed to pull DNS info from MXroute.</div>`;
        spfEl.textContent = "v=spf1 include:mxroute.com -all";
        dkimEl.textContent = "Error loading DKIM key";
    }
}

function updateDnsHealthHeader(health) {
    const statusEl = document.getElementById("dns-health-status");
    const textEl = document.getElementById("dns-health-status-text");
    if (!statusEl || !textEl) return;

    if (!health) {
        statusEl.className = "status-indicator";
        textEl.textContent = "No domain selected";
        return;
    }

    const labels = {
        healthy: { className: "status-indicator success", text: "DNS Healthy" },
        degraded: { className: "status-indicator warning", text: "DNS Degraded" },
        unhealthy: { className: "status-indicator danger", text: "DNS Issues Detected" }
    };
    const cfg = labels[health.overall] || labels.degraded;
    const mxrouteNote = health.mxroute_reachable === false ? " · MXroute unreachable" : "";
    statusEl.className = cfg.className;
    textEl.textContent = `${cfg.text}${mxrouteNote}`;
}

async function loadDnsHealth(domain) {
    if (!domain) {
        updateDnsHealthHeader(null);
        return;
    }

    const summaryEl = document.getElementById("dns-health-summary");
    const checksEl = document.getElementById("dns-health-checks");

    try {
        const result = await apiRequest(`/api/domains/${encodeURIComponent(domain)}/dns/health`);
        if (!result.success || !result.data) {
            throw new Error(result.error?.message || "Health check failed");
        }

        const health = result.data;
        updateDnsHealthHeader(health);

        if (summaryEl) {
            const summaryMap = {
                healthy: "All required DNS records look good in public DNS.",
                degraded: "Mail may work, but some recommended records need attention.",
                unhealthy: "Critical DNS records are missing or incorrect."
            };
            summaryEl.textContent = summaryMap[health.overall] || summaryMap.degraded;
        }

        if (checksEl) {
            checksEl.innerHTML = "";
            Object.values(health.checks || {}).forEach(check => {
                const item = document.createElement("div");
                item.className = `dns-health-item ${check.status}`;
                const icon = check.status === "pass" ? "✅" : check.status === "warn" ? "⚠️" : "❌";
                item.innerHTML = `
                    <div class="dns-health-item-title">${icon} ${escapeHtml(check.label)}</div>
                    <div class="dns-health-item-message">${escapeHtml(check.message)}</div>
                `;
                checksEl.appendChild(item);
            });
        }
    } catch (err) {
        updateDnsHealthHeader({ overall: "unhealthy", mxroute_reachable: false });
        if (summaryEl) {
            summaryEl.textContent = `DNS health check failed: ${err.message}`;
        }
        if (checksEl) {
            checksEl.innerHTML = "";
        }
    }
}

// 5.7 Email Accounts Management
async function loadEmailsList(domain) {
    const tbody = document.getElementById("emails-list-tbody");
    tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--color-muted);">Querying mailboxes...</td></tr>';
    
    try {
        const result = await apiRequest(`/api/domains/${domain}/email-accounts`);
        tbody.innerHTML = "";
        
        if (result.success && result.data && result.data.length > 0) {
            result.data.forEach(account => {
                const tr = document.createElement("tr");
                
                // Formulate storage progress bar
                const quotaVal = account.quota === 0 ? "Unlimited" : `${account.quota} MB`;
                const quotaPercent = account.quota === 0 ? 0 : Math.min(100, (account.usage / account.quota) * 100);
                const quotaColor = quotaPercent > 90 ? "danger" : (quotaPercent > 75 ? "warning" : "");
                
                // Outbound limits progress
                const limitVal = account.limit;
                const sentPercent = Math.min(100, (account.sent / account.limit) * 100);
                
                tr.innerHTML = `
                    <td>
                        <div style="font-weight: 600;">${escapeHtml(account.username)}@${escapeHtml(domain)}</div>
                        ${account.suspended ? '<span style="font-size:0.75rem; color: var(--danger); font-weight:500;">🚫 Suspended</span>' : ''}
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
                        <div class="flex-row" style="justify-content: flex-end; gap: 0.5rem;">
                            <button class="btn btn-secondary btn-sm" onclick="openPasswordModal(${jsString(account.username)})">🔑 Pass</button>
                            <button class="btn btn-secondary btn-sm" onclick="openQuotaModal(${jsString(account.username)}, ${Number(account.quota)}, ${Number(account.limit)})">⚙️ Limit</button>
                            <button class="btn btn-secondary btn-sm" onclick="handleToggleSuspend(${jsString(account.username)}, ${account.suspended ? "true" : "false"})">${account.suspended ? '🟢 Activate' : '🚫 Suspend'}</button>
                            <button class="btn btn-danger btn-sm" onclick="handleDeleteEmail(${jsString(account.username)})">🗑️ Delete</button>
                        </div>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--color-muted);">No mailboxes found for this domain.</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--danger);">Failed to load email accounts: ${escapeHtml(err.message)}</td></tr>`;
    }
}

// Check if domain has mail hosting enabled and update the UI overlay
async function checkDomainMailHostingStatus(domain) {
    const emailOverlay = document.getElementById("email-hosting-disabled-overlay");
    const forwardersOverlay = document.getElementById("forwarders-hosting-disabled-overlay");
    const spamOverlay = document.getElementById("spam-hosting-disabled-overlay");
    
    try {
        const result = await apiRequest(`/api/domains/${domain}`);
        if (result.success && result.data) {
            const displayMode = result.data.mail_hosting ? "none" : "flex";
            if (emailOverlay) emailOverlay.style.display = displayMode;
            if (forwardersOverlay) forwardersOverlay.style.display = displayMode;
            if (spamOverlay) spamOverlay.style.display = displayMode;
        } else {
            if (emailOverlay) emailOverlay.style.display = "none";
            if (forwardersOverlay) forwardersOverlay.style.display = "none";
            if (spamOverlay) spamOverlay.style.display = "none";
        }
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

// Create Email Account Submit
document.getElementById("form-create-email").addEventListener("submit", async (e) => {
    e.preventDefault();
    const usernameInput = document.getElementById("create-email-username");
    const passwordInput = document.getElementById("create-email-password");
    const quotaInput = document.getElementById("create-email-quota");
    const limitInput = document.getElementById("create-email-limit");
    
    const username = usernameInput.value.trim().toLowerCase();
    const password = passwordInput.value;
    const quota = parseInt(quotaInput.value);
    const limit = parseInt(limitInput.value);
    
    if (!username || !password) return;
    
    const submitBtn = document.getElementById("btn-provision-submit");
    submitBtn.disabled = true;
    submitBtn.textContent = "⌛ Provisioning...";
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/email-accounts`, "POST", {
            username,
            password,
            quota,
            limit
        });
        
        // Show Credentials card
        document.getElementById("out-email-addr").textContent = `${username}@${activeDomain}`;
        document.getElementById("out-email-pass").textContent = password;
        document.getElementById("out-imap-host").textContent = `mail.${activeDomain}`;
        document.getElementById("out-smtp-host").textContent = `mail.${activeDomain}`;
        document.getElementById("out-webmail-url").textContent = `https://webmail.${activeDomain}`;
        
        document.getElementById("credentials-output-card").style.display = "block";
        document.getElementById("credentials-output-card").scrollIntoView({ behavior: "smooth" });
        
        showAlert("success", `Mailbox ${username}@${activeDomain} created successfully!`);
        
        // Reset Form
        usernameInput.value = "";
        passwordInput.value = "";
        quotaInput.value = 1024;
        document.getElementById("create-email-quota-val").textContent = "1024 MB";
        limitInput.value = 9600;
        document.getElementById("create-email-limit-val").textContent = "9600 / day";
        
        // Reset password rules visualizer
        document.querySelectorAll("#create-email-requirements li").forEach(li => {
            li.classList.remove("valid");
            li.innerHTML = `✖ ${li.textContent.slice(2)}`;
        });
        
        await loadEmailsList(activeDomain);
        await loadAccountQuota();
    } catch (err) {
        showAlert("error", err.message);
    } finally {
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

// Delete Email Account
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
        await loadEmailsList(activeDomain);
        await loadAccountQuota();
    } catch (err) {
        showAlert("error", err.message);
    }
}

// Toggle Email Account Suspension
async function handleToggleSuspend(username, isSuspended) {
    const suspended = isSuspended === true || isSuspended === "true";
    const actionText = suspended ? "activate" : "suspend";
    const emailAddress = `${username}@${activeDomain}`;
    const confirmed = await showConfirm({
        title: suspended ? "Activate Mailbox" : "Suspend Mailbox",
        message: `Are you sure you want to ${actionText} ${emailAddress}?`,
        confirmLabel: suspended ? "Activate" : "Suspend",
        variant: suspended ? "primary" : "danger"
    });
    if (!confirmed) return;
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/email-accounts/${username}`, "PATCH", { suspended: !suspended });
        showAlert("success", `Mailbox ${username}@${activeDomain} ${actionText}d successfully.`);
        await loadEmailsList(activeDomain);
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
        li.innerHTML = `✖ ${li.textContent.slice(2)}`;
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
        await loadEmailsList(activeDomain);
    } catch (err) {
        showAlert("error", err.message);
    }
});


// 5.8 Forwarders Management
async function loadForwardersList(domain) {
    const tbody = document.getElementById("forwarders-list-tbody");
    tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">Loading forwarders...</td></tr>';
    
    try {
        const result = await apiRequest(`/api/domains/${domain}/forwarders`);
        tbody.innerHTML = "";
        
        if (result.success && result.data && result.data.length > 0) {
            result.data.forEach(forwarder => {
                const tr = document.createElement("tr");
                const destHtml = forwarder.destinations.map(d => `<div style="font-size:0.85rem; color:var(--color-secondary);">${escapeHtml(d)}</div>`).join('');
                
                tr.innerHTML = `
                    <td><strong>${escapeHtml(forwarder.alias)}@${escapeHtml(domain)}</strong></td>
                    <td>${destHtml}</td>
                    <td style="text-align: right;">
                        <button class="btn btn-danger btn-sm" onclick="handleDeleteForwarder(${jsString(forwarder.alias)})">Remove</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">No forwarders active for this domain.</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--danger);">Failed to load forwarders: ${escapeHtml(err.message)}</td></tr>`;
    }
}

// Create Forwarder Submit
document.getElementById("form-create-forwarder").addEventListener("submit", async (e) => {
    e.preventDefault();
    const aliasInput = document.getElementById("forwarder-alias");
    const destsInput = document.getElementById("forwarder-destinations");
    
    const alias = aliasInput.value.trim().toLowerCase();
    const destinations = destsInput.value.split(',').map(d => d.trim()).filter(d => d);
    
    if (!alias || destinations.length === 0) return;
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/forwarders`, "POST", { alias, destinations });
        showAlert("success", `Forwarder for ${alias}@${activeDomain} created!`);
        aliasInput.value = "";
        destsInput.value = "";
        await loadForwardersList(activeDomain);
    } catch (err) {
        showAlert("error", err.message);
    }
});

// Delete Forwarder
async function handleDeleteForwarder(alias) {
    const forwarderAddress = `${alias}@${activeDomain}`;
    const confirmed = await showTypedConfirm({
        title: "Delete Forwarder",
        message: `Remove the forwarder for ${forwarderAddress}?`,
        expectedValue: forwarderAddress,
        confirmLabel: "Delete Forwarder",
        inputLabel: "Type the forwarder email address to confirm"
    });
    if (!confirmed) return;
    try {
        await apiRequest(`/api/domains/${activeDomain}/forwarders/${alias}`, "DELETE");
        showAlert("success", `Forwarder ${alias}@${activeDomain} deleted.`);
        await loadForwardersList(activeDomain);
    } catch (err) {
        showAlert("error", err.message);
    }
}


// 5.9 Spam Control Panel
async function loadSpamSettings(domain) {
    const scoreSlider = document.getElementById("spam-high-score");
    const scoreLbl = document.getElementById("spam-high-score-val");
    
    try {
        const result = await apiRequest(`/api/domains/${domain}/spam/settings`);
        if (result.success && result.data) {
            const score = result.data.high_score;
            scoreSlider.value = score;
            scoreLbl.textContent = score;
        }
    } catch (err) {
        console.warn("Could not load spam settings:", err);
    }
    
    // Load Whitelist & Blacklist
    await Promise.all([
        loadSpamWhitelist(domain),
        loadSpamBlacklist(domain)
    ]);
}

// Spam Score Slider Updater
document.getElementById("spam-high-score").addEventListener("input", (e) => {
    document.getElementById("spam-high-score-val").textContent = e.target.value;
});

// Spam Settings Update Submit
document.getElementById("form-spam-settings").addEventListener("submit", async (e) => {
    e.preventDefault();
    const highScore = parseInt(document.getElementById("spam-high-score").value);
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/spam/settings`, "PATCH", { high_score: highScore });
        showAlert("success", "Spam score threshold updated.");
    } catch (err) {
        showAlert("error", err.message);
    }
});

// Whitelist loader
async function loadSpamWhitelist(domain) {
    const tbody = document.getElementById("whitelist-tbody");
    tbody.innerHTML = '<tr><td colspan="2" style="text-align: center; color: var(--color-muted);">Loading whitelist...</td></tr>';
    
    try {
        const result = await apiRequest(`/api/domains/${domain}/spam/whitelist`);
        tbody.innerHTML = "";
        
        if (result.success && result.data && result.data.length > 0) {
            result.data.forEach(entry => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td><strong>${escapeHtml(entry)}</strong></td>
                    <td style="text-align: right;">
                        <button class="btn btn-danger btn-sm btn-icon" onclick="handleRemoveSpamList('whitelist', ${jsString(entry)})">×</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="2" style="text-align: center; color: var(--color-muted);">No whitelist entries</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="2" style="text-align: center; color: var(--danger);">Error loading whitelist</td></tr>';
    }
}

// Add Whitelist Entry Submit
document.getElementById("form-whitelist-add").addEventListener("submit", async (e) => {
    e.preventDefault();
    const entryInput = document.getElementById("whitelist-entry");
    const entry = entryInput.value.trim();
    if (!entry) return;
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/spam/whitelist`, "POST", { entry });
        showAlert("success", `Added "${entry}" to whitelist.`);
        entryInput.value = "";
        await loadSpamWhitelist(activeDomain);
    } catch (err) {
        showAlert("error", err.message);
    }
});

// Blacklist loader
async function loadSpamBlacklist(domain) {
    const tbody = document.getElementById("blacklist-tbody");
    tbody.innerHTML = '<tr><td colspan="2" style="text-align: center; color: var(--color-muted);">Loading blacklist...</td></tr>';
    
    try {
        const result = await apiRequest(`/api/domains/${domain}/spam/blacklist`);
        tbody.innerHTML = "";
        
        if (result.success && result.data && result.data.length > 0) {
            result.data.forEach(entry => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td><strong>${escapeHtml(entry)}</strong></td>
                    <td style="text-align: right;">
                        <button class="btn btn-danger btn-sm btn-icon" onclick="handleRemoveSpamList('blacklist', ${jsString(entry)})">×</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="2" style="text-align: center; color: var(--color-muted);">No blacklist entries</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="2" style="text-align: center; color: var(--danger);">Error loading blacklist</td></tr>';
    }
}

// Add Blacklist Entry Submit
document.getElementById("form-blacklist-add").addEventListener("submit", async (e) => {
    e.preventDefault();
    const entryInput = document.getElementById("blacklist-entry");
    const entry = entryInput.value.trim();
    if (!entry) return;
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/spam/blacklist`, "POST", { entry });
        showAlert("success", `Added "${entry}" to blacklist.`);
        entryInput.value = "";
        await loadSpamBlacklist(activeDomain);
    } catch (err) {
        showAlert("error", err.message);
    }
});

// Remove Whitelist/Blacklist Entry
async function handleRemoveSpamList(type, entry) {
    const confirmed = await showConfirm({
        title: `Remove from ${type}`,
        message: `Remove "${entry}" from the spam ${type}?`,
        confirmLabel: "Remove"
    });
    if (!confirmed) return;
    try {
        // Encode entry for URL safeness (since it may contain symbols/wildcards)
        const encodedEntry = encodeURIComponent(entry);
        await apiRequest(`/api/domains/${activeDomain}/spam/${type}/${encodedEntry}`, "DELETE");
        showAlert("success", `Removed "${entry}" from ${type}.`);
        if (type === "whitelist") {
            await loadSpamWhitelist(activeDomain);
        } else {
            await loadSpamBlacklist(activeDomain);
        }
    } catch (err) {
        showAlert("error", err.message);
    }
}


// --- 6. Global Domain Selector Initialization ---
async function initDomainDropdowns() {
    const select = document.getElementById("global-domain-select");
    
    try {
        const result = await apiRequest("/api/domains");
        select.innerHTML = "";
        
        if (result.success && result.data && result.data.length > 0) {
            result.data.forEach(domain => {
                const option = document.createElement("option");
                option.value = domain;
                option.textContent = domain;
                select.appendChild(option);
            });
            
            // Set first domain as active if not already set, or preserve current if still exists
            if (!activeDomain || !result.data.includes(activeDomain)) {
                activeDomain = result.data[0];
            }
            select.value = activeDomain;
            
            await loadDnsHealth(activeDomain);
            // Load initial page data
            await triggerDataRefresh();
        } else {
            const option = document.createElement("option");
            option.value = "";
            if (currentUser && !currentUser.is_admin) {
                option.textContent = "No domains delegated to you";
                select.appendChild(option);
                activeDomain = "";
                showAlert("warning", "No domains have been delegated to your account. Please contact an administrator.");
            } else {
                option.textContent = "No domains found (Go to Domains Tab)";
                select.appendChild(option);
                activeDomain = "";
                showAlert("warning", "No domains found. Please configure a domain first in the Domains tab.");
            }
        }
    } catch (err) {
        select.innerHTML = '<option value="">Error loading domains</option>';
        showAlert("error", "Failed to retrieve account domains list from server.");
    }
}

// Dropdown Change Handler
document.getElementById("global-domain-select").addEventListener("change", async (e) => {
    activeDomain = e.target.value;
    await loadDnsHealth(activeDomain);
    await triggerDataRefresh();
});

// 5.8 Access Control & Delegations UI handlers
async function loadDelegationsPage() {
    const listBody = document.getElementById("delegations-list-tbody");
    listBody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">Querying access delegations...</td></tr>';
    
    const checklist = document.getElementById("delegation-domains-checklist");
    checklist.innerHTML = '<div style="color: var(--color-muted); font-size: 0.9rem;">Loading available domains...</div>';
    
    try {
        // Fetch all domains from backend for the checkboxes
        const domainsRes = await apiRequest("/api/domains");
        if (domainsRes.success && domainsRes.data) {
            checklist.innerHTML = "";
            
            // Add static "*" (All Domains / Admin Access) option at the top
            const adminLabel = document.createElement("label");
            adminLabel.className = "flex-row align-center";
            adminLabel.style.cursor = "pointer";
            adminLabel.style.fontSize = "0.9rem";
            adminLabel.style.color = "var(--accent)";
            adminLabel.style.fontWeight = "600";
            adminLabel.innerHTML = `
                <input type="checkbox" name="delegated-domain-cb" value="*" style="width: auto; height: auto; margin: 0;">
                <span>⭐ Admin</span>
            `;
            checklist.appendChild(adminLabel);
            
            if (domainsRes.data.length > 0) {
                domainsRes.data.forEach(domain => {
                    const label = document.createElement("label");
                    label.className = "flex-row align-center";
                    label.style.cursor = "pointer";
                    label.style.fontSize = "0.9rem";
                    const checkbox = document.createElement("input");
                    checkbox.type = "checkbox";
                    checkbox.name = "delegated-domain-cb";
                    checkbox.value = domain;
                    checkbox.style.width = "auto";
                    checkbox.style.height = "auto";
                    checkbox.style.margin = "0";
                    const span = document.createElement("span");
                    span.textContent = domain;
                    label.appendChild(checkbox);
                    label.appendChild(span);
                    checklist.appendChild(label);
                });
            }
        }
        
        // Fetch delegations list
        const delegationsRes = await apiRequest("/api/admin/delegations");
        listBody.innerHTML = "";
        
        if (delegationsRes.success && delegationsRes.data && delegationsRes.data.length > 0) {
            delegationsRes.data.forEach(item => {
                const tr = document.createElement("tr");
                
                // Format domains display
                let domainsStr = "";
                if (item.domains.includes("*")) {
                    domainsStr = '<span style="color: var(--accent); font-weight: 600;">⭐ Admin</span>';
                } else if (item.domains.length > 0) {
                    domainsStr = item.domains.map(escapeHtml).join(", ");
                } else {
                    domainsStr = '<span style="color: var(--color-muted); font-style: italic;">None</span>';
                }
                
                // 1. Email Cell
                const emailTd = document.createElement("td");
                const emailStrong = document.createElement("strong");
                emailStrong.textContent = item.email;
                emailTd.appendChild(emailStrong);
                tr.appendChild(emailTd);
                
                // 2. Domains Cell
                const domainsTd = document.createElement("td");
                domainsTd.style.maxWidth = "300px";
                domainsTd.style.wordBreak = "break-all";
                domainsTd.innerHTML = domainsStr;
                tr.appendChild(domainsTd);
                
                // 3. Action Cell
                const actionTd = document.createElement("td");
                actionTd.style.textAlign = "right";
                
                const wrapper = document.createElement("div");
                wrapper.className = "flex-row";
                wrapper.style.justifyContent = "flex-end";
                wrapper.style.gap = "0.5rem";
                
                // Edit Button
                const editBtn = document.createElement("button");
                editBtn.className = "btn btn-secondary btn-sm";
                editBtn.innerHTML = "⚙️ Edit";
                editBtn.addEventListener("click", () => {
                    handleEditDelegation(item.email, item.domains);
                });
                wrapper.appendChild(editBtn);
                
                // Revoke Button
                const revokeBtn = document.createElement("button");
                revokeBtn.className = "btn btn-danger btn-sm";
                revokeBtn.innerHTML = "Revoke";
                if (currentUser && currentUser.email.toLowerCase() === item.email.toLowerCase()) {
                    revokeBtn.disabled = true;
                    revokeBtn.title = "You cannot revoke your own access.";
                    revokeBtn.style.opacity = "0.5";
                    revokeBtn.style.cursor = "not-allowed";
                } else {
                    revokeBtn.addEventListener("click", () => {
                        handleDeleteDelegation(item.email);
                    });
                }
                wrapper.appendChild(revokeBtn);
                
                actionTd.appendChild(wrapper);
                tr.appendChild(actionTd);
                
                listBody.appendChild(tr);
            });
        } else {
            listBody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: var(--color-muted);">No delegations configured yet.</td></tr>';
        }
    } catch (err) {
        listBody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--danger);">Failed to load delegations: ${escapeHtml(err.message)}</td></tr>`;
        checklist.innerHTML = `<div style="color: var(--danger); font-size: 0.9rem;">Failed to load domains: ${escapeHtml(err.message)}</div>`;
    }
}

function handleEditDelegation(email, domains) {
    document.getElementById("delegation-email").value = email;
    const passInput = document.getElementById("delegation-password");
    if (passInput) passInput.value = "";
    const checkboxes = document.querySelectorAll('input[name="delegated-domain-cb"]');
    checkboxes.forEach(cb => {
        cb.checked = domains.includes(cb.value);
    });
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
    const email = emailInput.value.trim().toLowerCase();
    const passInput = document.getElementById("delegation-password");
    const password = passInput ? passInput.value : "";
    const checkboxes = document.querySelectorAll('input[name="delegated-domain-cb"]:checked');
    const domains = Array.from(checkboxes).map(cb => cb.value);
    
    if (!email) return;
    
    try {
        const payload = { email, domains };
        if (password) payload.password = password;
        
        await apiRequest("/api/admin/delegations", "POST", payload);
        showAlert("success", `Permissions updated for ${email}.`);
        emailInput.value = "";
        if (passInput) passInput.value = "";
        document.querySelectorAll('input[name="delegated-domain-cb"]').forEach(cb => cb.checked = false);
        await loadDelegationsPage();
    } catch (err) {
        showAlert("error", err.message);
    }
});

// On DOM Loaded
document.addEventListener("DOMContentLoaded", async () => {
    initConfirmModals();

    const refreshDnsHealthBtn = document.getElementById("btn-refresh-dns-health");
    if (refreshDnsHealthBtn) {
        refreshDnsHealthBtn.addEventListener("click", async () => {
            if (!activeDomain) {
                showAlert("warning", "Select a domain first.");
                return;
            }
            refreshDnsHealthBtn.disabled = true;
            refreshDnsHealthBtn.textContent = "⌛ Checking...";
            try {
                await loadDnsHealth(activeDomain);
                showAlert("success", "DNS health rechecked.");
            } catch (err) {
                showAlert("error", err.message);
            } finally {
                refreshDnsHealthBtn.textContent = "🔄 Recheck DNS";
                refreshDnsHealthBtn.disabled = false;
            }
        });
    }

    // 1. Fetch current user context
    try {
        const meResult = await apiRequest("/api/me");
        if (meResult && meResult.success) {
            currentUser = meResult.user;
            const oidcEnabled = meResult.oidc_enabled;
            
            if (currentUser) {
                // Update User Profile UI details
                document.getElementById("user-email").textContent = currentUser.email;
                const roleBadge = document.getElementById("user-role-badge");
                roleBadge.textContent = currentUser.is_admin ? "Admin" : "User";
                roleBadge.style.background = currentUser.is_admin ? "rgba(92, 221, 141, 0.2)" : "rgba(99, 102, 241, 0.2)";
                roleBadge.style.color = currentUser.is_admin ? "var(--accent)" : "#a5b4fc";
                document.getElementById("user-profile-container").style.display = "block";
                
                // Hide features for standard users
                if (!currentUser.is_admin) {
                    document.getElementById("nav-tab-domains").style.display = "none";
                    document.getElementById("nav-tab-delegations").style.display = "none";
                    document.getElementById("sidebar-quota-container").style.display = "none";
                    document.getElementById("dash-quota-card").style.display = "none";
                } else {
                    document.getElementById("nav-tab-delegations").style.display = "flex";
                }
            }
        }
    } catch (e) {
        console.warn("Could not retrieve user OIDC profile:", e);
    }

    // 2. Fetch overall quotas (if admin)
    if (!currentUser || currentUser.is_admin) {
        await loadAccountQuota();
    }
    
    // 3. Populate domains dropdown
    await initDomainDropdowns();
    
    // 4. Check Cloudflare integration status (if admin)
    if (!currentUser || currentUser.is_admin) {
        try {
            const cfStatus = await apiRequest("/api/cloudflare/status");
            if (cfStatus && cfStatus.configured) {
                document.getElementById("cf-option-container").style.display = "block";
                document.getElementById("cf-option-missing").style.display = "none";
            } else {
                document.getElementById("cf-option-container").style.display = "none";
                document.getElementById("cf-option-missing").style.display = "block";
            }
        } catch (e) {
            console.warn("Could not retrieve Cloudflare integration status:", e);
        }
    }

    // 5. Load Active Theme Preference
    loadTheme();

    // 6. Setup theme select card event listeners
    document.querySelectorAll(".theme-select-card").forEach(card => {
        card.addEventListener("click", () => {
            const theme = card.getAttribute("data-theme");
            setTheme(theme);
            showAlert("success", `Workspace theme changed to ${card.querySelector("div:last-child").textContent}`);
        });
    });

    // 7. Setup system settings form submission listener
    const settingsForm = document.getElementById("form-system-settings");
    if (settingsForm) {
        settingsForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const submitBtn = document.getElementById("btn-save-system-settings");
            submitBtn.disabled = true;
            submitBtn.textContent = "⌛ Saving Settings...";
            
            const payload = {
                OIDC_ENABLED: document.getElementById("setting-oidc-enabled").value,
                OIDC_SCOPES: document.getElementById("setting-oidc-scopes").value.trim(),
                OIDC_DISCOVERY_URL: document.getElementById("setting-oidc-discovery-url").value.trim(),
                OIDC_REDIRECT_URI: document.getElementById("setting-oidc-redirect-uri").value.trim(),
                OIDC_CLIENT_ID: document.getElementById("setting-oidc-client-id").value.trim(),
                OIDC_CLIENT_SECRET: document.getElementById("setting-oidc-client-secret").value,
                OIDC_ADMIN_USERS: document.getElementById("setting-oidc-admin-users").value.trim(),
                OIDC_ADMIN_GROUP: document.getElementById("setting-oidc-admin-group").value.trim(),
                MX_SERVER: document.getElementById("setting-mx-server").value.trim(),
                MX_USER: document.getElementById("setting-mx-user").value.trim(),
                MX_API_KEY: document.getElementById("setting-mx-api-key").value,
                CF_API_TOKEN: document.getElementById("setting-cf-api-token").value,
                CF_ACCOUNT_ID: document.getElementById("setting-cf-account-id").value.trim(),
                ADMIN_USER: document.getElementById("setting-admin-user").value.trim(),
                ADMIN_PASSWORD: document.getElementById("setting-admin-password").value
            };
            
            try {
                const res = await apiRequest("/api/admin/settings", "POST", payload);
                if (res.success) {
                    showAlert("success", "System settings successfully updated!");
                } else {
                    showAlert("error", res.error.message || "Failed to update system settings.");
                }
            } catch (err) {
                showAlert("error", `Error updating settings: ${err.message}`);
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = "💾 Save System Settings";
            }
        });
    }
});

// --- 7. Theming & Settings Controller ---

function loadTheme() {
    const activeTheme = localStorage.getItem("workspace-theme") || "emerald";
    setTheme(activeTheme, false);
}

function setTheme(theme, save = true) {
    const themes = ["emerald", "indigo", "crimson", "amber", "amethyst", "cyberpunk"];
    
    // Remove all theme classes from body
    themes.forEach(t => document.body.classList.remove(`theme-${t}`));
    
    // Apply selected theme class
    document.body.classList.add(`theme-${theme}`);
    
    if (save) {
        localStorage.setItem("workspace-theme", theme);
    }
    
    // Highlight selected card if settings page is loaded
    document.querySelectorAll(".theme-select-card").forEach(card => {
        if (card.getAttribute("data-theme") === theme) {
            card.classList.add("active");
        } else {
            card.classList.remove("active");
        }
    });
}

async function loadSettingsPage() {
    // Refresh theme active selector highlighted state
    const activeTheme = localStorage.getItem("workspace-theme") || "emerald";
    setTheme(activeTheme, false);
    
    if (currentUser && currentUser.is_admin) {
        document.getElementById("system-settings-card").style.display = "block";
        
        try {
            const res = await apiRequest("/api/admin/settings");
            if (res.success && res.data) {
                const settings = res.data;
                
                // Populate forms
                document.getElementById("setting-oidc-enabled").value = settings.OIDC_ENABLED || "true";
                document.getElementById("setting-oidc-scopes").value = settings.OIDC_SCOPES || "openid email profile groups";
                document.getElementById("setting-oidc-discovery-url").value = settings.OIDC_DISCOVERY_URL || "";
                document.getElementById("setting-oidc-redirect-uri").value = settings.OIDC_REDIRECT_URI || "";
                document.getElementById("setting-oidc-client-id").value = settings.OIDC_CLIENT_ID || "";
                document.getElementById("setting-oidc-client-secret").value = settings.OIDC_CLIENT_SECRET || "";
                document.getElementById("setting-oidc-admin-users").value = settings.OIDC_ADMIN_USERS || "";
                document.getElementById("setting-oidc-admin-group").value = settings.OIDC_ADMIN_GROUP || "administrators";
                
                document.getElementById("setting-mx-server").value = settings.MX_SERVER || "";
                document.getElementById("setting-mx-user").value = settings.MX_USER || "";
                document.getElementById("setting-mx-api-key").value = settings.MX_API_KEY || "";
                
                document.getElementById("setting-cf-api-token").value = settings.CF_API_TOKEN || "";
                document.getElementById("setting-cf-account-id").value = settings.CF_ACCOUNT_ID || "";
                
                document.getElementById("setting-admin-user").value = settings.ADMIN_USER || "admin";
                document.getElementById("setting-admin-password").value = settings.ADMIN_PASSWORD || "";
            }
        } catch (err) {
            showAlert("error", `Failed to load settings: ${err.message}`);
        }
    } else {
        document.getElementById("system-settings-card").style.display = "none";
    }
}