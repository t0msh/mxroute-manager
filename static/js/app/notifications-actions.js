async function openNotificationTargetModal(editIndex = null) {
    resetNotificationTargetModal();
    notificationEditIndex = editIndex;
    const title = document.getElementById("modal-notification-target-title");
    if (title) {
        title.textContent = editIndex === null ? "Add notification target" : "Edit notification target";
    }

    if (editIndex !== null && notificationTargets[editIndex]) {
        const target = notificationTargets[editIndex];
        const labelInput = document.getElementById("notification-target-label");
        if (labelInput) labelInput.value = target.label || "";

        const select = document.getElementById("notification-builder-service");
        const serviceId = target.service_id || target.service || "";
        if (select && serviceId) {
            select.value = serviceId;
        }

        try {
            const parsePayload = {
                service_id: serviceId,
                cred_env: target.cred_env || null,
            };
            // Saved targets load masked URLs; read the full URL from the database on the server.
            if ((target.url || "").includes("***")) {
                parsePayload.target_index = editIndex;
            } else {
                parsePayload.url = target.url;
            }
            const parseRes = await apiRequest("/api/admin/notifications/builder/parse", "POST", parsePayload);
            if (parseRes?.success && parseRes.data) {
                const parsed = parseRes.data;
                if (select && parsed.service) {
                    select.value = parsed.service;
                }
                renderNotificationBuilderFields(select?.value || parsed.service, parsed.fields || {});
                showNotificationCompilePreview({
                    url: parsed.url || target.url,
                    masked_url: parsed.masked_url || target.url,
                    service: parsed.service || serviceId,
                    cred_env: target.cred_env || null,
                });
            } else {
                renderNotificationBuilderFields(select?.value || notificationBuilderServices[0]?.id);
                showAlert("warning", parseRes?.error?.message || "Could not parse target URL into builder fields.");
            }
        } catch (err) {
            renderNotificationBuilderFields(select?.value || notificationBuilderServices[0]?.id);
            showAlert("error", err.message);
        }
    } else if (notificationBuilderServices.length) {
        const select = document.getElementById("notification-builder-service");
        if (select && !select.value) {
            select.value = notificationBuilderServices[0].id;
            renderNotificationBuilderFields(select.value);
        }
    }

    openModal("modal-notification-target");
}

async function compileNotificationUrlFromBuilder() {
    const serviceId = document.getElementById("notification-builder-service")?.value;
    if (!serviceId) return;
    const fields = collectNotificationBuilderFields();
    const tokenInEnv = document.getElementById("notification-store-token-env")?.checked || false;
    const result = await apiRequest("/api/admin/notifications/builder/compile", "POST", {
        service_id: serviceId,
        fields,
        token_in_env: tokenInEnv,
    });
    if (!result?.success) {
        showAlert("error", result?.error?.message || "Failed to compile URL.");
        return;
    }
    showNotificationCompilePreview(result.data);
}

async function recompileWithTokenEnvPreference() {
    if (!notificationCompiledResult) return;
    const serviceId = document.getElementById("notification-builder-service")?.value;
    if (!serviceId || !notificationCredEnvMap[serviceId]) return;
    await compileNotificationUrlFromBuilder();
}

async function validatePastedNotificationUrl() {
    const url = document.getElementById("notification-paste-url")?.value.trim();
    if (!url) {
        showAlert("error", "Enter an Apprise URL first.");
        return;
    }
    const result = await apiRequest("/api/admin/notifications/builder/compile", "POST", {
        service_id: "custom",
        fields: { url },
    });
    if (!result?.success) {
        showAlert("error", result?.error?.message || "Invalid Apprise URL.");
        return;
    }
    showNotificationCompilePreview(result.data);
}

function saveCompiledNotificationTarget() {
    if (!notificationCompiledResult?.url) {
        showAlert("error", "Generate or validate a URL first.");
        return;
    }
    const label = document.getElementById("notification-target-label")?.value.trim()
        || notificationCompiledResult.service
        || "Notification target";
    const storeInEnv = document.getElementById("notification-store-token-env")?.checked || false;
    const target = {
        label,
        url: notificationCompiledResult.url,
        service: notificationCompiledResult.service || "",
        service_id: notificationCompiledResult.service || "",
        cred_env: storeInEnv ? (notificationCompiledResult.cred_env || null) : null,
    };
    if (notificationEditIndex === null) {
        notificationTargets.push(target);
    } else {
        notificationTargets[notificationEditIndex] = target;
    }
    renderNotificationTargets();
    closeModal("modal-notification-target");
    showAlert("success", "Target added. Click Save Notifications to persist.");
}

async function copyNotificationEnvSnippet() {
    const serviceId = notificationCompiledResult?.service;
    const tokenInEnv = document.getElementById("notification-store-token-env")?.checked;
    if (!tokenInEnv || !notificationCompiledResult?.env_snippet) {
        await recompileWithTokenEnvPreference();
    }
    const snippet = notificationCompiledResult?.env_snippet
        || document.getElementById("notification-env-snippet")?.value;
    if (!snippet) {
        showAlert("error", "Enable \"Store token in .env\" and generate a URL with a token first.");
        return;
    }
    try {
        await navigator.clipboard.writeText(snippet);
        showAlert("success", `Copied ${notificationCompiledResult?.cred_env || "credential"}. Paste into .env and restart the app.`);
    } catch (err) {
        const textarea = document.getElementById("notification-env-snippet");
        if (textarea) {
            textarea.value = snippet;
            textarea.style.display = "block";
            textarea.select();
        }
        showAlert("info", "Copy the snippet manually from the text box.");
    }
}

async function applyNotificationSettingsToForm(data) {
    if (!data) return;

    notificationTargets = (data.targets || []).map((target) => ({
        label: target.label || "",
        url: target.url || "",
        service: target.service || "",
        service_id: target.service_id || target.service || "",
        cred_env: target.cred_env || null,
        cred_env_configured: Boolean(target.cred_env_configured),
    }));

    const enabledToggle = document.getElementById("setting-notifications-enabled");
    if (enabledToggle) {
        enabledToggle.checked = Boolean(data.enabled);
    }

    const monitorToggle = document.getElementById("setting-dns-monitor-enabled");
    const monitorInterval = document.getElementById("setting-dns-monitor-interval");
    if (monitorToggle) {
        monitorToggle.checked = Boolean(data.dns_monitor?.enabled);
    }
    if (monitorInterval) {
        const hours = Number(data.dns_monitor?.interval_hours || 24);
        monitorInterval.value = String(hours);
    }

    const quotaToggle = document.getElementById("setting-quota-monitor-enabled");
    const quotaInterval = document.getElementById("setting-quota-monitor-interval");
    const quotaPercent = document.getElementById("setting-quota-monitor-quota-percent");
    const sendPercent = document.getElementById("setting-quota-monitor-send-percent");
    if (quotaToggle) {
        quotaToggle.checked = Boolean(data.quota_monitor?.enabled);
    }
    if (quotaInterval) {
        quotaInterval.value = String(Number(data.quota_monitor?.interval_hours || 12));
    }
    if (quotaPercent) {
        quotaPercent.value = String(Number(data.quota_monitor?.quota_percent || 90));
    }
    if (sendPercent) {
        sendPercent.value = String(Number(data.quota_monitor?.send_percent || 90));
    }

    renderNotificationTargets();
    renderNotificationActionsGrid(data.actions || []);
}

async function loadNotificationSettings() {
    if (!currentUser?.is_admin) return;
    try {
        const [settingsRes, actionsRes, builderRes] = await Promise.all([
            apiRequest("/api/admin/notifications"),
            apiRequest("/api/admin/notifications/actions"),
            apiRequest("/api/admin/notifications/builder"),
        ]);
        if (actionsRes?.success) {
            notificationActionGroups = actionsRes.data?.groups || [];
        }
        if (builderRes?.success) {
            notificationBuilderServices = builderRes.data?.services || [];
            notificationCredEnvMap = builderRes.data?.cred_env_map || {};
            notificationResetSmtpConfigured = Boolean(builderRes.data?.reset_smtp_configured);
            const select = document.getElementById("notification-builder-service");
            if (select) {
                setTrustedHtml(
                    select,
                    notificationBuilderServices
                        .map(
                            (service) =>
                                `<option value="${escapeHtml(service.id)}">${escapeHtml(service.label)}</option>`
                        )
                        .join("")
                );
                if (notificationBuilderServices.length) {
                    select.value = notificationBuilderServices[0].id;
                    renderNotificationBuilderFields(select.value);
                }
            }
        }
        if (settingsRes?.success && settingsRes.data) {
            await applyNotificationSettingsToForm(settingsRes.data);
            const envHint = document.getElementById("notification-env-hint");
            if (envHint) {
                envHint.textContent = "Tip: if you're uncomfortable storing tokens in the database, they can be stored in .env instead (one variable per service, e.g. APPRISE_CRED_NTFY).";
            }
        }
    } catch (err) {
        showAlert("error", `Failed to load notifications: ${err.message}`);
    }
}

async function saveNotificationSettings() {
    const btn = document.getElementById("btn-save-notifications");
    if (btn) {
        btn.disabled = true;
        setTrustedHtml(btn, btnLabel("save", "Saving...", true));
    }
    try {
        const payload = {
            enabled: Boolean(document.getElementById("setting-notifications-enabled")?.checked),
            targets: notificationTargets,
            actions: getSelectedNotificationActions(),
            dns_monitor: {
                enabled: Boolean(document.getElementById("setting-dns-monitor-enabled")?.checked),
                interval_hours: Number(document.getElementById("setting-dns-monitor-interval")?.value || 24),
            },
            quota_monitor: {
                enabled: Boolean(document.getElementById("setting-quota-monitor-enabled")?.checked),
                interval_hours: Number(document.getElementById("setting-quota-monitor-interval")?.value || 12),
                quota_percent: Number(document.getElementById("setting-quota-monitor-quota-percent")?.value || 90),
                send_percent: Number(document.getElementById("setting-quota-monitor-send-percent")?.value || 90),
            },
        };
        const result = await apiRequest("/api/admin/notifications", "POST", payload);
        if (result?.success) {
            showAlert("success", "Notification settings saved.");
            if (result.data) {
                await applyNotificationSettingsToForm(result.data);
            } else {
                await loadNotificationSettings();
            }
        } else {
            showAlert("error", result?.error?.message || "Failed to save notification settings.");
        }
    } catch (err) {
        showAlert("error", `Error saving notifications: ${err.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            setTrustedHtml(btn, btnLabel("save", "Save Notifications"));
        }
    }
}

function initNotificationSettingsEvents() {
    if (notificationEventsBound) return;
    notificationEventsBound = true;

    document.getElementById("btn-add-notification-target")?.addEventListener("click", () => openNotificationTargetModal());
    document.getElementById("btn-save-notifications")?.addEventListener("click", saveNotificationSettings);
    document.getElementById("btn-notification-compile")?.addEventListener("click", compileNotificationUrlFromBuilder);
    document.getElementById("btn-notification-validate-paste")?.addEventListener("click", validatePastedNotificationUrl);
    document.getElementById("btn-notification-save-target")?.addEventListener("click", saveCompiledNotificationTarget);
    document.getElementById("btn-notification-copy-env")?.addEventListener("click", copyNotificationEnvSnippet);
    document.getElementById("modal-notification-target-close")?.addEventListener("click", () => closeModal("modal-notification-target"));
    document.getElementById("modal-notification-target-cancel")?.addEventListener("click", () => closeModal("modal-notification-target"));

    document.getElementById("notification-builder-service")?.addEventListener("change", (event) => {
        renderNotificationBuilderFields(event.target.value);
    });
    document.getElementById("notification-store-token-env")?.addEventListener("change", recompileWithTokenEnvPreference);

    document.querySelectorAll(".notification-tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".notification-tab").forEach((btn) => btn.classList.remove("active"));
            tab.classList.add("active");
            const name = tab.getAttribute("data-notification-tab");
            document.getElementById("notification-tab-build").style.display = name === "build" ? "block" : "none";
            document.getElementById("notification-tab-paste").style.display = name === "paste" ? "block" : "none";
        });
    });

    document.getElementById("notification-targets-list")?.addEventListener("click", (event) => {
        const editBtn = event.target.closest(".btn-edit-notification-target");
        const removeBtn = event.target.closest(".btn-remove-notification-target");
        if (editBtn) {
            openNotificationTargetModal(Number(editBtn.getAttribute("data-index")));
        }
        if (removeBtn) {
            const index = Number(removeBtn.getAttribute("data-index"));
            notificationTargets.splice(index, 1);
            renderNotificationTargets();
        }
    });

    document.getElementById("btn-notify-preset-destructive")?.addEventListener("click", async () => {
        const res = await apiRequest("/api/admin/notifications/actions");
        const destructive = new Set(res?.data?.destructive_action_ids || []);
        setSelectedNotificationActions(Array.from(document.querySelectorAll(".notification-action-checkbox")).map((el) => el.value).filter((id) => destructive.has(id)));
    });
    document.getElementById("btn-notify-preset-all")?.addEventListener("click", () => {
        document.querySelectorAll(".notification-action-checkbox").forEach((input) => { input.checked = true; });
    });
    document.getElementById("btn-notify-preset-clear")?.addEventListener("click", () => {
        document.querySelectorAll(".notification-action-checkbox").forEach((input) => { input.checked = false; });
    });

    document.getElementById("btn-test-notifications")?.addEventListener("click", async () => {
        const btn = document.getElementById("btn-test-notifications");
        if (btn) {
            btn.disabled = true;
            setTrustedHtml(btn, btnLabel("bell", "Sending...", true));
        }
        try {
            const result = await apiRequest("/api/admin/notifications/test", "POST", {});
            if (result?.success) {
                showAlert("success", result.message || "Test notification sent.");
            } else {
                showAlert("error", result?.error?.message || "Failed to send test notification.");
            }
        } catch (err) {
            showAlert("error", `Error sending test notification: ${err.message}`);
        } finally {
            if (btn) {
                btn.disabled = false;
                setTrustedHtml(btn, btnLabel("bell", "Send Test Notification"));
            }
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
                setSettingsBoolToggle("setting-oidc-enabled", settings.OIDC_ENABLED);
                document.getElementById("setting-oidc-scopes").value = settings.OIDC_SCOPES || "openid email profile groups";
                document.getElementById("setting-oidc-discovery-url").value = settings.OIDC_DISCOVERY_URL || "";
                document.getElementById("setting-oidc-redirect-uri").value = settings.OIDC_REDIRECT_URI || "";
                document.getElementById("setting-oidc-client-id").value = settings.OIDC_CLIENT_ID || "";
                renderSecretStatus("setting-oidc-client-secret-status", settings.OIDC_CLIENT_SECRET_configured);
                document.getElementById("setting-oidc-admin-users").value = settings.OIDC_ADMIN_USERS || "";
                document.getElementById("setting-oidc-admin-group").value = settings.OIDC_ADMIN_GROUP || "administrators";
                
                document.getElementById("setting-mx-server").value = settings.MX_SERVER || "";
                document.getElementById("setting-mx-user").value = settings.MX_USER || "";
                renderSecretStatus("setting-mx-api-key-status", settings.MX_API_KEY_configured);
                
                renderSecretStatus("setting-cf-api-token-status", settings.CF_API_TOKEN_configured);
                document.getElementById("setting-cf-account-id").value = settings.CF_ACCOUNT_ID || "";
                
                document.getElementById("setting-admin-user").value = settings.ADMIN_USER || "admin";
                document.getElementById("setting-admin-password").value = "";

                setSettingsBoolToggle("setting-mailbox-reset-enabled", settings.MAILBOX_RESET_ENABLED);
                document.getElementById("setting-reset-smtp-host").value = settings.RESET_SMTP_HOST || "";
                document.getElementById("setting-reset-smtp-port").value = settings.RESET_SMTP_PORT || "587";
                document.getElementById("setting-reset-smtp-user").value = settings.RESET_SMTP_USER || "";
                document.getElementById("setting-reset-smtp-from").value = settings.RESET_SMTP_FROM || "";
                setSettingsBoolToggle("setting-reset-smtp-use-tls", settings.RESET_SMTP_USE_TLS ?? "true");
                renderSecretStatus(
                    "setting-reset-smtp-password-status",
                    settings.RESET_SMTP_PASSWORD_configured,
                    "Password set via .env"
                );

                const contactInput = document.getElementById("setting-admin-contact-email");
                if (contactInput) {
                    contactInput.value = currentUser?.contact_email || "";
                }
                renderSmtpTestStatus(currentUser);
            }
        } catch (err) {
            showAlert("error", `Failed to load settings: ${err.message}`);
        }
    } else {
        document.getElementById("system-settings-card").style.display = "none";
    }
}

