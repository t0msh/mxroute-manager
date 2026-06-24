function downloadMailboxExportCsv() {
    if (!mailboxesListDomain || !mailboxesListAll?.length) {
        showAlert("warning", "No mailboxes loaded to export.");
        return;
    }
    const blob = new Blob(
        [buildMailboxExportCsv(mailboxesListAll, mailboxesListDomain)],
        { type: "text/csv" },
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `mailboxes-${mailboxesListDomain}-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
}

document.getElementById("btn-export-mailboxes-csv")?.addEventListener("click", downloadMailboxExportCsv);
