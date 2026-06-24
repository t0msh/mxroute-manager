const MAILBOX_IMPORT_CONCURRENCY = 3;
const MAILBOX_IMPORT_TEMPLATE = [
    "username,password,quota,limit,recovery_email",
    "alice,Abcd1234!,1024,9600,alice.personal@gmail.com",
    "bob,AnotherPass2!,1024,9600,",
].join("\n");

let mailboxImportPreviewRows = [];
let mailboxImportRunning = false;

function parseCsvLine(line) {
    const values = [];
    let current = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i += 1) {
        const char = line[i];
        if (char === '"') {
            if (inQuotes && line[i + 1] === '"') {
                current += '"';
                i += 1;
            } else {
                inQuotes = !inQuotes;
            }
            continue;
        }
        if (char === "," && !inQuotes) {
            values.push(current.trim());
            current = "";
            continue;
        }
        current += char;
    }
    values.push(current.trim());
    return values;
}

function parseMailboxCsvText(text) {
    const lines = String(text || "")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter((line) => line && !line.startsWith("#"));
    if (!lines.length) return [];

    const headers = parseCsvLine(lines[0]).map((header) => header.toLowerCase());
    return lines.slice(1).map((line, index) => {
        const values = parseCsvLine(line);
        const row = { _line: index + 2 };
        headers.forEach((header, colIndex) => {
            row[header] = values[colIndex] ?? "";
        });
        return row;
    });
}

function summarizeImportRows(rows) {
    return {
        total: rows.length,
        valid: rows.filter((row) => row.valid).length,
        invalid: rows.filter((row) => !row.valid).length,
        needs_password: rows.filter((row) => row.needs_password && !row.errors?.length).length,
        already_exists: rows.filter((row) => row.already_exists).length,
        duplicate_in_csv: rows.filter((row) => row.duplicate_in_csv).length,
    };
}

function buildExistingMailboxesMap() {
    const domain = String(activeDomain || mailboxesListDomain || "")
        .trim()
        .toLowerCase();
    if (!domain || !mailboxesListAll?.length) {
        return {};
    }
    const usernames = mailboxesListAll
        .map((account) => String(account.username || "").trim().toLowerCase())
        .filter(Boolean);
    return usernames.length ? { [domain]: usernames } : {};
}

function applyExistingMailboxFlags(rows) {
    const domainKey = String(activeDomain || mailboxesListDomain || "")
        .trim()
        .toLowerCase();
    if (!domainKey || !mailboxesListAll?.length) {
        return summarizeImportRows(rows);
    }
    const existing = new Set(
        mailboxesListAll
            .map((account) => String(account.username || "").trim().toLowerCase())
            .filter(Boolean),
    );
    const message = "Mailbox already exists on this domain.";
    rows.forEach((row) => {
        if (!row.username || row.duplicate_in_csv) {
            return;
        }
        const rowDomain = String(row.domain || domainKey).trim().toLowerCase();
        if (rowDomain !== domainKey) {
            return;
        }
        const username = String(row.username).trim().toLowerCase();
        if (!existing.has(username)) {
            return;
        }
        row.already_exists = true;
        row.valid = false;
        row.errors = (row.errors || []).includes(message)
            ? row.errors
            : [...(row.errors || []), message];
    });
    return summarizeImportRows(rows);
}

function setMailboxImportStep(step) {
    document.getElementById("mailbox-import-step-upload")?.style.setProperty(
        "display",
        step === "upload" ? "block" : "none",
    );
    document.getElementById("mailbox-import-step-preview")?.style.setProperty(
        "display",
        step === "preview" ? "block" : "none",
    );
}

function renderMailboxImportPreview(rows, summary) {
    const tbody = document.getElementById("mailbox-import-preview-tbody");
    if (!tbody) return;

    if (!rows.length) {
        setTrustedHtml(
            tbody,
            '<tr><td colspan="5" style="text-align: center; color: var(--color-muted);">No rows parsed.</td></tr>',
        );
        return;
    }

    setTrustedHtml(tbody, "");
    rows.forEach((row) => {
        const tr = document.createElement("tr");
        const address = row.domain && row.username ? `${row.username}@${row.domain}` : "—";
        let statusHtml;
        if (row.already_exists) {
            statusHtml = '<span class="status-indicator warning"><span class="dot"></span> Already exists</span>';
        } else if (row.valid) {
            statusHtml = '<span class="status-indicator success"><span class="dot"></span> Ready</span>';
        } else if (row.needs_password && !row.errors?.length) {
            statusHtml = '<span class="status-indicator warning"><span class="dot"></span> Needs password</span>';
        } else {
            statusHtml = '<span class="status-indicator danger"><span class="dot"></span> Invalid</span>';
        }
        const errorText = (row.errors || []).join(" ") || (row.needs_password ? "Password will be generated." : "");
        tr.innerHTML = `
            <td>${escapeHtml(String(row.line || "—"))}</td>
            <td>${escapeHtml(address)}</td>
            <td>${escapeHtml(row.quota ?? "")}</td>
            <td>${statusHtml}</td>
            <td style="font-size: 0.8rem; color: var(--color-secondary);">${escapeHtml(errorText)}</td>
        `;
        tbody.appendChild(tr);
    });

    const summaryEl = document.getElementById("mailbox-import-preview-summary");
    if (summaryEl && summary) {
        const parts = [`${summary.valid} ready`, `${summary.invalid} invalid`];
        if (summary.already_exists) {
            parts.push(`${summary.already_exists} already exist`);
        }
        if (summary.duplicate_in_csv) {
            parts.push(`${summary.duplicate_in_csv} duplicate in CSV`);
        }
        parts.push(`${summary.total} total`);
        summaryEl.textContent = parts.join(", ");
    }

    const startBtn = document.getElementById("btn-mailbox-import-start");
    if (startBtn) {
        startBtn.disabled = summary.valid === 0 || mailboxImportRunning;
    }
}

function updateMailboxImportProgress({ done, total, created, failed, skipped }) {
    const percent = total ? Math.round((done / total) * 100) : 0;
    const bar = document.getElementById("mailbox-import-progress-bar");
    const label = document.getElementById("mailbox-import-progress-label");
    const counts = document.getElementById("mailbox-import-progress-counts");
    if (bar) bar.style.width = `${percent}%`;
    if (label) label.textContent = `${done} / ${total} processed (${percent}%)`;
    if (counts) {
        counts.textContent = `${created} created · ${failed} failed · ${skipped} skipped`;
    }
}

function appendMailboxImportLog(entry) {
    const log = document.getElementById("mailbox-import-log");
    if (!log) return;
    const li = document.createElement("li");
    li.className = `import-log-item import-log-${entry.status}`;
    li.textContent = entry.message;
    log.appendChild(li);
    log.scrollTop = log.scrollHeight;
}

function buildMailboxImportResultsCsv(results) {
    const header = "line,mailbox,status,message,password\n";
    const lines = results.map((row) => {
        const cols = [
            row.line ?? "",
            row.mailbox ?? "",
            row.status ?? "",
            row.message ?? "",
            row.password ?? "",
        ];
        return cols.map((value) => `"${String(value).replace(/"/g, '""')}"`).join(",");
    });
    return header + lines.join("\n");
}

function downloadMailboxImportResults(results) {
    const blob = new Blob([buildMailboxImportResultsCsv(results)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `mailbox-import-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
}

async function runMailboxImport(validRows) {
    if (mailboxImportRunning || !validRows.length) return;

    mailboxImportRunning = true;
    const progressCard = document.getElementById("mailbox-import-progress-card");
    const log = document.getElementById("mailbox-import-log");
    if (progressCard) progressCard.style.display = "block";
    if (log) setTrustedHtml(log, "");

    closeModal("modal-mailbox-import");

    const total = validRows.length;
    let done = 0;
    let created = 0;
    let failed = 0;
    const results = [];

    updateMailboxImportProgress({ done, total, created, failed, skipped: 0 });

    await window.Mxm.utils.mapWithConcurrency(validRows, MAILBOX_IMPORT_CONCURRENCY, async (row) => {
        const domain = row.domain;
        const mailbox = `${row.username}@${domain}`;
        const payload = {
            username: row.username,
            password: row.password,
            quota: row.quota,
            limit: row.limit,
        };
        if (row.recovery_email) payload.recovery_email = row.recovery_email;

        let status = "failed";
        let message = "";
        try {
            await apiRequest(`/api/domains/${domain}/email-accounts`, "POST", payload);
            created += 1;
            status = "created";
            message = `${mailbox} created`;
        } catch (err) {
            failed += 1;
            message = `${mailbox}: ${err.message}`;
        }

        done += 1;
        results.push({
            line: row.line,
            mailbox,
            status,
            message,
            password: status === "created" ? row.password : "",
        });
        updateMailboxImportProgress({ done, total, created, failed, skipped: 0 });
        appendMailboxImportLog({ status, message });
    });

    mailboxImportRunning = false;
    const downloadBtn = document.getElementById("btn-mailbox-import-download-results");
    if (downloadBtn) {
        downloadBtn.style.display = "inline-flex";
        downloadBtn.onclick = () => downloadMailboxImportResults(results);
    }

    if (activeDomain) {
        invalidateApiCache(`/api/domains/${activeDomain}/email-accounts`);
        await loadEmailsList(activeDomain, { force: true });
    }
    await loadAccountQuota({ force: true });

    if (failed === 0) {
        showAlert("success", `Imported ${created} mailbox${created === 1 ? "" : "es"}.`);
    } else {
        showAlert("warning", `Import finished: ${created} created, ${failed} failed.`);
    }
}

async function previewMailboxImportFromFile() {
    const fileInput = document.getElementById("mailbox-import-file");
    const file = fileInput?.files?.[0];
    if (!file) {
        showAlert("warning", "Choose a CSV file first.");
        return;
    }
    if (!activeDomain) {
        showAlert("warning", "Select a domain first.");
        return;
    }

    const generateMissing = !!document.getElementById("mailbox-import-generate-passwords")?.checked;
    let text;
    try {
        text = await file.text();
    } catch {
        showAlert("error", "Could not read the CSV file.");
        return;
    }

    const parsed = parseMailboxCsvText(text);
    if (!parsed.length) {
        showAlert("warning", "No data rows found in CSV.");
        return;
    }

    if (generateMissing) {
        parsed.forEach((row) => {
            if (!String(row.password || "").trim()) {
                row.password = generateRandomPassword();
            }
        });
    }

    const previewBtn = document.getElementById("btn-mailbox-import-preview");
    if (previewBtn) {
        previewBtn.disabled = true;
        setTrustedHtml(previewBtn, btnLabel("search", "Validating...", true));
    }

    try {
        if (
            !mailboxesListAll.length
            || String(mailboxesListDomain || "").toLowerCase()
                !== String(activeDomain || "").toLowerCase()
        ) {
            await loadEmailsList(activeDomain, { force: false });
        }

        const existingByDomain = buildExistingMailboxesMap();
        const result = await apiRequest("/api/email-accounts/import/preview", "POST", {
            default_domain: activeDomain,
            existing_by_domain: existingByDomain,
            rows: parsed,
        });
        mailboxImportPreviewRows = result.data?.rows || [];
        const summary = applyExistingMailboxFlags(mailboxImportPreviewRows);
        renderMailboxImportPreview(mailboxImportPreviewRows, summary);
        setMailboxImportStep("preview");
    } catch (err) {
        showAlert("error", err.message);
    } finally {
        if (previewBtn) {
            previewBtn.disabled = false;
            setTrustedHtml(previewBtn, btnLabel("search", "Preview import"));
        }
    }
}

function setMailboxImportFileName(file) {
    const nameEl = document.getElementById("mailbox-import-file-name");
    if (!nameEl) return;
    nameEl.textContent = file?.name || "No file chosen";
    nameEl.classList.toggle("is-empty", !file);
}

function openMailboxImportModal() {
    if (!activeDomain) {
        showAlert("warning", "Select a domain first.");
        return;
    }
    const fileInput = document.getElementById("mailbox-import-file");
    if (fileInput) fileInput.value = "";
    setMailboxImportFileName(null);
    mailboxImportPreviewRows = [];
    setMailboxImportStep("upload");
    renderMailboxImportPreview([], { total: 0, valid: 0, invalid: 0 });
    document.getElementById("mailbox-import-domain-hint").textContent = activeDomain;
    openModal("modal-mailbox-import");
}

document.getElementById("btn-open-mailbox-import")?.addEventListener("click", openMailboxImportModal);

document.getElementById("mailbox-import-file")?.addEventListener("change", (event) => {
    setMailboxImportFileName(event.target.files?.[0] || null);
});

document.getElementById("btn-mailbox-import-template")?.addEventListener("click", () => {
    const blob = new Blob([MAILBOX_IMPORT_TEMPLATE], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "mailbox-import-template.csv";
    link.click();
    URL.revokeObjectURL(url);
});

document.getElementById("btn-mailbox-import-preview")?.addEventListener("click", previewMailboxImportFromFile);

document.getElementById("btn-mailbox-import-back")?.addEventListener("click", () => {
    setMailboxImportStep("upload");
});

document.getElementById("btn-mailbox-import-start")?.addEventListener("click", async () => {
    const ready = mailboxImportPreviewRows.filter((row) => row.valid);
    if (!ready.length) {
        showAlert("warning", "No valid rows to import.");
        return;
    }
    closeModal("modal-mailbox-import");
    const confirmed = await showConfirm({
        title: "Import mailboxes",
        message: `Create ${ready.length} mailbox${ready.length === 1 ? "" : "es"}? Rows marked "Already exists" will be skipped.`,
        confirmLabel: "Start import",
        variant: "primary",
    });
    if (!confirmed) {
        setMailboxImportStep("preview");
        openModal("modal-mailbox-import");
        return;
    }
    await runMailboxImport(ready);
});

document.getElementById("btn-mailbox-import-dismiss-progress")?.addEventListener("click", () => {
    const card = document.getElementById("mailbox-import-progress-card");
    if (card) card.style.display = "none";
});
