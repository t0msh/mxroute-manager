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
            setTrustedHtml(refreshDnsHealthBtn, btnLabel("arrow-clockwise", "Checking...", true));
            try {
                await loadDnsHealth(activeDomain, { force: true });
                showAlert("success", "DNS health rechecked.");
            } catch (err) {
                showAlert("error", err.message);
            } finally {
                setTrustedHtml(refreshDnsHealthBtn, btnLabel("arrow-clockwise", "Recheck DNS"));
                refreshDnsHealthBtn.disabled = false;
            }
        });
    }

    const refreshDomainsStatusBtn = document.getElementById("btn-refresh-domains-status");
    if (refreshDomainsStatusBtn) {
        refreshDomainsStatusBtn.addEventListener("click", () => refreshDomainsListStatus());
    }

    document.getElementById("btn-bulk-fix-dns")?.addEventListener("click", () => handleBulkFixDns());

    // 1. Fetch current user context
    try {
        const meResult = await apiRequest("/api/me");
        if (meResult && meResult.success) {
            currentUser = meResult.user;
            oidcEnabled = !!meResult.oidc_enabled;
            
            if (currentUser) {
                document.getElementById("user-email").textContent = currentUser.email;
                const roleBadge = document.getElementById("user-role-badge");
                roleBadge.textContent = currentUser.is_admin ? "Admin" : "User";
                roleBadge.style.background = currentUser.is_admin
                    ? `rgba(var(--accent-rgb), 0.2)`
                    : "rgba(99, 102, 241, 0.2)";
                roleBadge.style.color = currentUser.is_admin ? "var(--accent)" : "#a5b4fc";
                document.getElementById("user-profile-container").style.display = "block";
                applyUserPermissionsUI();
            }
        }
    } catch (e) {
        console.warn("Could not retrieve user OIDC profile:", e);
    }

    // 2. Fetch overall quotas (if admin)
    if (currentUser?.is_admin) {
        await loadAccountQuota();
    }
    
    // 3. Populate domains dropdown
    await initDomainDropdowns();
    initResetPortal();
    initMailboxActionMenus();
    initDomainActionMenus();
    initSecondaryTableActionMenus();
    
    // 4. Domain DNS wizard (admin or users with dns permission)
    const canManageDns = currentUser?.is_admin || getUserPermissionUnion().has("dns");
    if (canManageDns) {
        initDomainDmarcUi();
        initSetupWizard();
        applyDomainsSectionVisibility();
        if (currentUser?.is_admin) {
            try {
                const cfStatus = await apiRequest("/api/cloudflare/status");
                setupCfConfigured = !!(cfStatus && cfStatus.configured);
                const cfMissing = document.getElementById("setup-cf-missing");
                if (cfMissing) {
                    cfMissing.style.display = setupCfConfigured ? "none" : "block";
                }
                if (setupWizardStep === 4 && setupCurrentHealth) {
                    renderSetupDnsChecks(setupCurrentHealth);
                }
            } catch (e) {
                console.warn("Could not retrieve Cloudflare integration status:", e);
            }
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
            setTrustedHtml(submitBtn, btnLabel("save", "Saving Settings...", true));
            
            const payload = {
                OIDC_ENABLED: getSettingsBoolToggle("setting-oidc-enabled"),
                OIDC_SCOPES: document.getElementById("setting-oidc-scopes").value.trim(),
                OIDC_DISCOVERY_URL: document.getElementById("setting-oidc-discovery-url").value.trim(),
                OIDC_REDIRECT_URI: document.getElementById("setting-oidc-redirect-uri").value.trim(),
                OIDC_CLIENT_ID: document.getElementById("setting-oidc-client-id").value.trim(),
                OIDC_ADMIN_USERS: document.getElementById("setting-oidc-admin-users").value.trim(),
                OIDC_ADMIN_GROUP: document.getElementById("setting-oidc-admin-group").value.trim(),
                MX_SERVER: document.getElementById("setting-mx-server").value.trim(),
                MX_USER: document.getElementById("setting-mx-user").value.trim(),
                CF_ACCOUNT_ID: document.getElementById("setting-cf-account-id").value.trim(),
                ADMIN_USER: document.getElementById("setting-admin-user").value.trim(),
                MAILBOX_RESET_ENABLED: getSettingsBoolToggle("setting-mailbox-reset-enabled"),
                RESET_SMTP_HOST: document.getElementById("setting-reset-smtp-host").value.trim(),
                RESET_SMTP_PORT: document.getElementById("setting-reset-smtp-port").value.trim(),
                RESET_SMTP_USER: document.getElementById("setting-reset-smtp-user").value.trim(),
                RESET_SMTP_FROM: document.getElementById("setting-reset-smtp-from").value.trim(),
                RESET_SMTP_USE_TLS: getSettingsBoolToggle("setting-reset-smtp-use-tls"),
            };

            const newAdminPassword = document.getElementById("setting-admin-password").value;
            if (newAdminPassword.trim()) {
                payload.ADMIN_PASSWORD = newAdminPassword;
            }

            try {
                const contactSaved = await saveAdminContactEmail();
                if (!contactSaved) {
                    submitBtn.disabled = false;
                    setTrustedHtml(submitBtn, btnLabel("save", "Save System Settings"));
                    return;
                }

                const res = await apiRequest("/api/admin/settings", "POST", payload);
                if (res.success) {
                    showAlert("success", "System settings successfully updated!");
                    document.getElementById("setting-admin-password").value = "";
                    await loadSettingsPage();
                } else {
                    showAlert("error", res.error.message || "Failed to update system settings.");
                }
            } catch (err) {
                showAlert("error", `Error updating settings: ${err.message}`);
            } finally {
                submitBtn.disabled = false;
                setTrustedHtml(submitBtn, btnLabel("save", "Save System Settings"));
            }
        });
    }

    const testSmtpBtn = document.getElementById("btn-test-smtp-settings");
    if (testSmtpBtn) {
        testSmtpBtn.addEventListener("click", async () => {
            testSmtpBtn.disabled = true;
            setTrustedHtml(testSmtpBtn, btnLabel("send", "Sending...", true));
            try {
                const contactSaved = await saveAdminContactEmail();
                if (!contactSaved) return;

                const result = await apiRequest("/api/admin/settings/test-smtp", "POST", collectSmtpTestPayload());
                if (result.success) {
                    showAlert("success", result.message || "Test email sent.");
                } else {
                    showAlert("error", result.error?.message || "Failed to send test email.");
                }
            } catch (err) {
                showAlert("error", err.message);
            } finally {
                setTrustedHtml(testSmtpBtn, btnLabel("send", "Send Test Email"));
                renderSmtpTestStatus(currentUser);
            }
        });
    }
});
