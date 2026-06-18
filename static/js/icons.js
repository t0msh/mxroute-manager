/** Bootstrap Icons markup helpers for dynamic UI (self-hosted under /static/vendor/). */

export function icon(name, extraClass = "") {
    const cls = extraClass ? `bi bi-${name} ${extraClass}` : `bi bi-${name}`;
    return `<i class="${cls}" aria-hidden="true"></i>`;
}

export const ALERT_ICONS = {
    success: "check-circle-fill",
    error: "x-circle-fill",
    warning: "exclamation-triangle-fill",
    info: "info-circle-fill",
};

export const DNS_STATUS_ICONS = {
    pass: "check-circle-fill",
    pending: "hourglass-split",
    skipped: "dash",
    warn: "exclamation-triangle-fill",
    fail: "x-circle-fill",
};

export function dnsStatusIcon(status) {
    return icon(DNS_STATUS_ICONS[status] || "question-circle");
}

export function setReqIcon(el, valid) {
    const reqIcon = el.querySelector(".req-icon");
    if (reqIcon) {
        reqIcon.className = `bi bi-${valid ? "check" : "x"} req-icon`;
    }
}
