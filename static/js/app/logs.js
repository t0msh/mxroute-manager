async function loadNotificationsPage() {
    if (!currentUser?.is_admin) return;
    const card = document.getElementById("notifications-card");
    if (card) card.style.display = "block";
    initNotificationSettingsEvents();
    await loadNotificationSettings();
}

let logAutoRefreshInterval = null;
let logsCache = [];

async function loadLogsPage() {
    if (!currentUser || !currentUser.is_admin) return;

    const dateSelect = document.getElementById("logs-date-select");
    const limitSelect = document.getElementById("logs-limit-select");

    const selectedDate = dateSelect.value || "";
    const selectedLimit = limitSelect.value || "100";

    try {
        const url = `/api/admin/logs?date=${encodeURIComponent(selectedDate)}&limit=${encodeURIComponent(selectedLimit)}`;
        const res = await apiRequest(url);

        if (res.success && res.data) {
            logsCache = res.data.entries || [];
            const availableDates = res.data.available_dates || [];
            const currentDate = res.data.current_date || "";

            // Populate date selection dropdown if not already populated or if list changed
            const existingOptions = Array.from(dateSelect.options).map(o => o.value);
            const matchesAvailable = availableDates.length === existingOptions.length && availableDates.every((v, i) => v === existingOptions[i]);

            if (!matchesAvailable) {
                setTrustedHtml(dateSelect, "");
                availableDates.forEach(dateVal => {
                    const opt = document.createElement("option");
                    opt.value = dateVal;
                    opt.textContent = dateVal;
                    if (dateVal === currentDate) {
                        opt.selected = true;
                    }
                    dateSelect.appendChild(opt);
                });
            }

            renderLogsTable();
        }
    } catch (err) {
        console.error("Failed to load logs:", err);
        showAlert("error", `Failed to retrieve logs: ${err.message}`);
    }
}

function renderLogsTable() {
    const tbody = document.getElementById("logs-list-tbody");
    const filterQuery = document.getElementById("logs-search").value.trim().toLowerCase();

    setTrustedHtml(tbody, "");

    const filteredLogs = logsCache.filter(log => {
        if (!filterQuery) return true;
        const detailsStr = JSON.stringify(log.details || {}).toLowerCase();
        return (
            (log.timestamp || "").toLowerCase().includes(filterQuery) ||
            (log.user || "").toLowerCase().includes(filterQuery) ||
            (log.action || "").toLowerCase().includes(filterQuery) ||
            (log.target || "").toLowerCase().includes(filterQuery) ||
            detailsStr.includes(filterQuery)
        );
    });

    if (filteredLogs.length === 0) {
        setTrustedHtml(tbody, tablePlaceholderRowHtml(5, "No matching log entries found."));
        return;
    }

    filteredLogs.forEach(log => {
        const tr = document.createElement("tr");

        // Format ISO timestamp slightly
        let formattedTime = log.timestamp || "";
        try {
            const dt = new Date(log.timestamp);
            if (!isNaN(dt)) {
                formattedTime = dt.toISOString().replace("T", " ").substring(0, 19);
            }
        } catch (_) {}

        tr.innerHTML = `
            <td><code>${escapeHtml(formattedTime)}</code></td>
            <td><strong>${escapeHtml(log.user)}</strong></td>
            <td><span class="badge" style="font-size: 0.8rem; font-weight: 500; font-family: monospace; background: rgba(255,255,255,0.05); padding: 0.15rem 0.4rem; border-radius: 4px;">${escapeHtml(log.action)}</span></td>
            <td><code style="word-break: break-all;">${escapeHtml(log.target)}</code></td>
            <td>${window.Mxm.utils.formatAuditLogDetailsHtml(log.details)}</td>
        `;
        tbody.appendChild(tr);
    });
}

async function downloadAuditLogs() {
    const dateSelect = document.getElementById("logs-date-select");
    const formatSelect = document.getElementById("logs-download-format");
    const downloadBtn = document.getElementById("btn-download-logs");
    const date = dateSelect?.value;
    if (!date) {
        showAlert("warning", "No log date selected.");
        return;
    }

    const logFormat = formatSelect?.value || "csv";
    const url = `/api/admin/logs/download?date=${encodeURIComponent(date)}&format=${encodeURIComponent(logFormat)}`;

    if (downloadBtn) {
        downloadBtn.disabled = true;
        setTrustedHtml(downloadBtn, btnLabel("download", "Downloading...", true));
    }

    try {
        const response = await fetch(url);
        if (!response.ok) {
            let message = `HTTP ${response.status}`;
            try {
                const result = await response.json();
                message = result.error?.message || message;
            } catch (_) {}
            throw new Error(message);
        }

        const blob = await response.blob();
        const disposition = response.headers.get("Content-Disposition") || "";
        const match = disposition.match(/filename="?([^";\n]+)"?/);
        const fallbackExt = logFormat === "jsonl" ? "jsonl" : "csv";
        const filename = match?.[1] || `audit-${date}.${fallbackExt}`;
        const blobUrl = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = blobUrl;
        link.download = filename;
        link.click();
        URL.revokeObjectURL(blobUrl);
    } catch (err) {
        showAlert("error", `Failed to download logs: ${err.message}`);
    } finally {
        if (downloadBtn) {
            downloadBtn.disabled = false;
            setTrustedHtml(downloadBtn, btnLabel("download", "Download"));
        }
    }
}

function initLogsPageEvents() {
    const dateSelect = document.getElementById("logs-date-select");
    const limitSelect = document.getElementById("logs-limit-select");
    const searchInput = document.getElementById("logs-search");
    const autoRefreshCheckbox = document.getElementById("logs-auto-refresh");
    const refreshBtn = document.getElementById("btn-refresh-logs");
    const downloadBtn = document.getElementById("btn-download-logs");

    if (!dateSelect || !limitSelect || !searchInput || !autoRefreshCheckbox || !refreshBtn) return;

    downloadBtn?.addEventListener("click", downloadAuditLogs);

    dateSelect.addEventListener("change", loadLogsPage);
    limitSelect.addEventListener("change", loadLogsPage);
    searchInput.addEventListener("input", renderLogsTable);

    refreshBtn.addEventListener("click", async () => {
        refreshBtn.disabled = true;
        setTrustedHtml(refreshBtn, btnLabel("arrow-clockwise", "Loading...", true));
        try {
            await loadLogsPage();
        } finally {
            setTrustedHtml(refreshBtn, btnLabel("arrow-clockwise", "Reload Logs"));
            refreshBtn.disabled = false;
        }
    });

    autoRefreshCheckbox.addEventListener("change", () => {
        if (autoRefreshCheckbox.checked) {
            setupLogsAutoRefresh();
        } else {
            clearLogsAutoRefresh();
        }
    });

    // Clear auto refresh interval if tab is changed
    document.querySelectorAll(".nav-item").forEach(item => {
        item.addEventListener("click", () => {
            const tab = item.getAttribute("data-tab");
            if (tab !== "logs") {
                autoRefreshCheckbox.checked = false;
                clearLogsAutoRefresh();
            }
        });
    });
}

function setupLogsAutoRefresh() {
    clearLogsAutoRefresh();
    logAutoRefreshInterval = setInterval(async () => {
        const activeTab = document.querySelector(".nav-item.active")?.getAttribute("data-tab");
        if (activeTab === "logs") {
            await loadLogsPage();
        } else {
            clearLogsAutoRefresh();
        }
    }, 10000);
}

function clearLogsAutoRefresh() {
    if (logAutoRefreshInterval) {
        clearInterval(logAutoRefreshInterval);
        logAutoRefreshInterval = null;
    }
}

// Register Events
initLogsPageEvents();

document.getElementById("delegation-email")?.addEventListener("input", updateDelegationPasswordHint);
document.getElementById("delegation-password")?.addEventListener("input", updateDelegationPasswordHint);
