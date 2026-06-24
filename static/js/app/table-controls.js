const TABLE_PAGE_SIZES = [5, 10, 20];

function readTablePrefs(storageKey) {
    try {
        const raw = localStorage.getItem(storageKey);
        if (!raw) return { pageSize: 10, query: "", page: 1 };
        const parsed = JSON.parse(raw);
        const pageSize = TABLE_PAGE_SIZES.includes(parsed.pageSize) ? parsed.pageSize : 10;
        return {
            pageSize,
            query: String(parsed.query || ""),
            page: Math.max(1, parseInt(parsed.page, 10) || 1),
        };
    } catch {
        return { pageSize: 10, query: "", page: 1 };
    }
}

function writeTablePrefs(storageKey, prefs) {
    try {
        localStorage.setItem(storageKey, JSON.stringify(prefs));
    } catch {
        // ponytail: ignore storage quota / private mode
    }
}

function filterTableItems(items, query, getSearchText) {
    const needle = String(query || "").trim().toLowerCase();
    if (!needle) return items;
    return items.filter((item) => getSearchText(item).toLowerCase().includes(needle));
}

function paginateTableItems(items, page, pageSize) {
    const total = items.length;
    const pages = Math.max(1, Math.ceil(total / pageSize) || 1);
    const safePage = Math.min(Math.max(1, page), pages);
    const start = (safePage - 1) * pageSize;
    return {
        items: items.slice(start, start + pageSize),
        page: safePage,
        pages,
        total,
        startIndex: total ? start + 1 : 0,
        endIndex: total ? Math.min(start + pageSize, total) : 0,
    };
}

function mountTableControls(rootId, options = {}) {
    const root = document.getElementById(rootId);
    if (!root) return null;

    const storageKey = options.storageKey || rootId;
    let state = readTablePrefs(storageKey);
    let footerMeta = { page: 1, pages: 1, total: 0, startIndex: 0, endIndex: 0 };

    if (root.dataset.mounted !== "true") {
        root.dataset.mounted = "true";
        root.className = "table-controls";
        setTrustedHtml(root, `
            <input type="search" class="table-search-input" placeholder="${escapeHtml(options.placeholder || "Search...")}" autocomplete="off">
            <div class="table-controls-right">
                <label class="table-page-size-label">
                    Rows
                    <select class="table-page-size">
                        ${TABLE_PAGE_SIZES.map((size) => `<option value="${size}">${size}</option>`).join("")}
                    </select>
                </label>
                <div class="table-pagination">
                    <button type="button" class="btn btn-secondary btn-sm" data-page="prev" aria-label="Previous page">Prev</button>
                    <span class="table-page-info">0 results</span>
                    <button type="button" class="btn btn-secondary btn-sm" data-page="next" aria-label="Next page">Next</button>
                </div>
            </div>
        `);

        const searchInput = root.querySelector(".table-search-input");
        const pageSizeSelect = root.querySelector(".table-page-size");
        searchInput.value = state.query;
        pageSizeSelect.value = String(state.pageSize);

        searchInput.addEventListener("input", () => {
            state = { ...state, query: searchInput.value, page: 1 };
            writeTablePrefs(storageKey, state);
            options.onChange?.(state);
        });
        pageSizeSelect.addEventListener("change", () => {
            state = {
                ...state,
                pageSize: parseInt(pageSizeSelect.value, 10) || 10,
                page: 1,
            };
            writeTablePrefs(storageKey, state);
            options.onChange?.(state);
        });
        root.querySelector('[data-page="prev"]').addEventListener("click", () => {
            if (state.page <= 1) return;
            state = { ...state, page: state.page - 1 };
            writeTablePrefs(storageKey, state);
            options.onChange?.(state);
        });
        root.querySelector('[data-page="next"]').addEventListener("click", () => {
            if (state.page >= footerMeta.pages) return;
            state = { ...state, page: state.page + 1 };
            writeTablePrefs(storageKey, state);
            options.onChange?.(state);
        });
    }

    const searchInput = root.querySelector(".table-search-input");
    const pageSizeSelect = root.querySelector(".table-page-size");
    if (searchInput && searchInput.value !== state.query) searchInput.value = state.query;
    if (pageSizeSelect) pageSizeSelect.value = String(state.pageSize);

    return {
        getState: () => ({ ...state }),
        setState(patch) {
            state = { ...state, ...patch };
            if (searchInput && patch.query !== undefined) searchInput.value = state.query;
            if (pageSizeSelect && patch.pageSize !== undefined) {
                pageSizeSelect.value = String(state.pageSize);
            }
            writeTablePrefs(storageKey, state);
        },
        updateFooter(meta) {
            footerMeta = meta;
            const pageInfo = root.querySelector(".table-page-info");
            const prevBtn = root.querySelector('[data-page="prev"]');
            const nextBtn = root.querySelector('[data-page="next"]');
            if (pageInfo) {
                pageInfo.textContent = meta.total
                    ? `${meta.startIndex}–${meta.endIndex} of ${meta.total}`
                    : "0 results";
            }
            if (prevBtn) prevBtn.disabled = meta.page <= 1;
            if (nextBtn) nextBtn.disabled = meta.page >= meta.pages;
            if (meta.page !== state.page) {
                state = { ...state, page: meta.page };
                writeTablePrefs(storageKey, state);
            }
        },
    };
}

function applyTableView({ allItems, controls, getSearchText, renderItems }) {
    const state = controls.getState();
    const filtered = filterTableItems(allItems, state.query, getSearchText);
    const page = paginateTableItems(filtered, state.page, state.pageSize);
    renderItems(page.items, { filteredTotal: page.total, allTotal: allItems.length });
    controls.updateFooter(page);
    return page;
}
