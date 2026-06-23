
function loadTheme() {
    const activeTheme = localStorage.getItem("workspace-theme") || "emerald";
    setTheme(activeTheme, false);
}

function setTheme(theme, save = true) {
    const themes = window.Mxm?.themes?.THEME_IDS ?? [
        "emerald", "indigo", "crimson", "amber", "amethyst", "cyberpunk",
        "emerald-light", "indigo-light", "slate-light", "rose-light",
    ];
    const safeTheme = themes.includes(theme) ? theme : "emerald";
    
    themes.forEach(t => document.body.classList.remove(`theme-${t}`));
    
    // Apply selected theme class
    document.body.classList.add(`theme-${safeTheme}`);
    
    if (save) {
        localStorage.setItem("workspace-theme", safeTheme);
    }
    
    // Highlight selected card if settings page is loaded
    document.querySelectorAll(".theme-select-card").forEach(card => {
        if (card.getAttribute("data-theme") === safeTheme) {
            card.classList.add("active");
        } else {
            card.classList.remove("active");
        }
    });

    if (typeof updateThemedFavicon === "function") {
        updateThemedFavicon();
    }
}

function renderSecretStatus(elementId, configured, successText = "Configured via environment") {
    const el = document.getElementById(elementId);
    if (!el) return;
    setTrustedHtml(
        el,
        configured
            ? `<span class="status-indicator success"><span class="dot"></span> ${escapeHtml(successText)}</span>`
            : `<span class="status-indicator danger"><span class="dot"></span> Not configured</span>`
    );
}

function renderSmtpTestStatus(user) {
    const statusEl = document.getElementById("setting-smtp-test-status");
    const testBtn = document.getElementById("btn-test-smtp-settings");
    if (!statusEl || !testBtn) return;

    const notificationEmail = user?.notification_email;
    if (notificationEmail) {
        setTrustedHtml(statusEl, `<span class="status-indicator success"><span class="dot"></span> Test emails will be sent to <strong>${escapeHtml(notificationEmail)}</strong></span>`);
        testBtn.disabled = false;
    } else {
        setTrustedHtml(statusEl, `<span class="status-indicator danger"><span class="dot"></span> Add a contact email below (or sign in with an email address) to send test emails.</span>`);
        testBtn.disabled = true;
    }
}

function collectSmtpTestPayload() {
    const payload = {
        RESET_SMTP_HOST: document.getElementById("setting-reset-smtp-host").value.trim(),
        RESET_SMTP_PORT: document.getElementById("setting-reset-smtp-port").value.trim(),
        RESET_SMTP_USER: document.getElementById("setting-reset-smtp-user").value.trim(),
        RESET_SMTP_FROM: document.getElementById("setting-reset-smtp-from").value.trim(),
        RESET_SMTP_USE_TLS: getSettingsBoolToggle("setting-reset-smtp-use-tls"),
    };
    return payload;
}

async function saveAdminContactEmail() {
    const input = document.getElementById("setting-admin-contact-email");
    if (!input) return true;

    const nextValue = input.value.trim().toLowerCase();
    const currentValue = (currentUser?.contact_email || "").toLowerCase();
    if (nextValue === currentValue) return true;

    const result = await apiRequest("/api/me/profile", "PATCH", {
        contact_email: nextValue || null,
    });
    if (result?.success) {
        currentUser = {
            ...currentUser,
            contact_email: result.data?.contact_email || null,
            notification_email: result.data?.notification_email || null,
        };
        renderSmtpTestStatus(currentUser);
        return true;
    }
    showAlert("error", result?.error?.message || "Failed to save contact email.");
    return false;
}

let notificationTargets = [];
let notificationActionGroups = [];
let notificationBuilderServices = [];
let notificationCompiledResult = null;
let notificationEditIndex = null;
let notificationCredEnvMap = {};
let notificationResetSmtpConfigured = false;
let notificationEventsBound = false;

