// 5.3 Domain Details (Dashboard Overview)
async function loadDomainDetails(domain, { force = false } = {}) {
    if (!domain) return;
    const statsGrid = document.querySelector("#tab-dashboard .stats-grid");
    const firstLoad = !hasLoadedContent(document.getElementById("dash-mailboxes-count"));

    const renderDetails = (result, mailboxRes) => {
        if (result?.success && result.data) {
            const data = result.data;
            activeDomainMailHosting = !!data.mail_hosting;
            const mailStatusEl = document.getElementById("dash-mail-status");
            if (mailStatusEl) {
                setTrustedHtml(
                    mailStatusEl,
                    data.mail_hosting
                        ? `<span class="status-indicator success"><span class="dot"></span> Enabled</span>`
                        : `<span class="status-indicator danger"><span class="dot"></span> Disabled</span>`
                );
            }
            document.getElementById("dash-pointers-count").textContent = data.pointers ? data.pointers.length : 0;
            document.getElementById("dash-mailboxes-count").dataset.loaded = "true";
        }

        if (mailboxRes?.success && mailboxRes.data) {
            document.getElementById("dash-mailboxes-count").textContent = mailboxRes.data.length;
        } else if (mailboxRes) {
            document.getElementById("dash-mailboxes-count").textContent = 0;
        }
    };

    try {
        const detailsUrl = `/api/domains/${domain}`;
        const mailboxesUrl = `/api/domains/${domain}/email-accounts`;

        const result = await cachedFetch(detailsUrl, {
            force,
            onRefreshStart: () => setElementRefreshing(statsGrid, true),
            onRefreshEnd: () => setElementRefreshing(statsGrid, false),
            onUpdated: async (updated) => {
                const mailboxRes = apiCache.get(mailboxesUrl)?.data
                    || await cachedFetch(mailboxesUrl, { force: true });
                renderDetails(updated, mailboxRes);
            },
        });

        let mailboxRes = apiCache.get(mailboxesUrl)?.data;
        const mailboxesFresh = isCacheFresh(mailboxesUrl);
        if (!mailboxRes || force || !mailboxesFresh) {
            mailboxRes = await cachedFetch(mailboxesUrl, {
                force,
                onRefreshStart: () => setElementRefreshing(statsGrid, true),
                onRefreshEnd: () => setElementRefreshing(statsGrid, false),
            });
        }
        renderDetails(result, mailboxRes);
    } catch (err) {
        console.warn("Could not load domain details:", err);
        if (firstLoad) {
            document.getElementById("dash-mailboxes-count").textContent = "--";
        }
    }
}

// Toggle Mail Hosting status
document.getElementById("btn-toggle-mail-hosting").addEventListener("click", async () => {
    if (!activeDomain || activeDomainMailHosting === null) return;
    const nextState = !activeDomainMailHosting;
    
    try {
        await apiRequest(`/api/domains/${activeDomain}/mail-status`, "PATCH", { enabled: nextState });
        showAlert("success", `Mail hosting status updated successfully.`);
        invalidateDomainCache(activeDomain);
        await loadDomainDetails(activeDomain, { force: true });
    } catch (err) {
        showAlert("error", err.message);
    }
});

let setupWizardDomain = "";
let setupWizardStep = 1;
let setupCfConfigured = false;
let setupCurrentHealth = null;
let setupHealthPollTimer = null;
let setupHealthPollInFlight = false;
let setupHealthPollDeadline = 0;

