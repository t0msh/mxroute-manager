const MAILBOX_CSV_COLUMNS = [
    "username",
    "password",
    "quota",
    "limit",
    "recovery_email",
    "domain",
];
const MAILBOX_IMPORT_TEMPLATE = [
    MAILBOX_CSV_COLUMNS.join(","),
    "alice,Abcd1234!,1024,9600,alice.personal@gmail.com",
    "bob,AnotherPass2!,1024,9600,",
].join("\n");

function csvEscape(value) {
    const text = String(value ?? "");
    if (/[",\n\r]/.test(text)) {
        return `"${text.replace(/"/g, '""')}"`;
    }
    return text;
}

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

function buildMailboxExportCsv(accounts, domain) {
    const header = `${MAILBOX_CSV_COLUMNS.join(",")}\n`;
    const lines = (accounts || []).map((account) => {
        const cols = [
            account.username ?? "",
            "",
            account.quota ?? "",
            account.limit ?? "",
            account.recovery_email ?? "",
            domain ?? "",
        ];
        return cols.map(csvEscape).join(",");
    });
    return header + lines.join("\n");
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
