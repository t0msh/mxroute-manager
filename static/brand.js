const APP_LOGO_PATH = "/static/logo.svg";
const APP_THEMES = ["emerald", "indigo", "crimson", "amber", "amethyst", "cyberpunk"];

let _logoSvgTemplate = null;

function getAccentColor() {
    return getComputedStyle(document.body).getPropertyValue("--accent").trim() || "#5cdd8d";
}

function applyStoredTheme() {
    const theme = localStorage.getItem("workspace-theme") || "emerald";
    APP_THEMES.forEach(t => document.body.classList.remove(`theme-${t}`));
    document.body.classList.add(`theme-${theme}`);
    return theme;
}

async function loadLogoSvgTemplate() {
    if (_logoSvgTemplate) return _logoSvgTemplate;

    const version = document.querySelector('link[rel="stylesheet"][href*="style.css"]')?.href.match(/[?&]v=([^&]+)/)?.[1];
    const logoUrl = version ? `${APP_LOGO_PATH}?v=${encodeURIComponent(version)}` : APP_LOGO_PATH;
    const response = await fetch(logoUrl);
    if (!response.ok) {
        throw new Error("Failed to load logo.svg");
    }

    _logoSvgTemplate = await response.text();
    return _logoSvgTemplate;
}

async function updateThemedFavicon() {
    try {
        let svgText = await loadLogoSvgTemplate();
        const accent = getAccentColor();
        svgText = svgText
            .replace(/fill="currentColor"/g, `fill="${accent}"`)
            .replace(/fill:currentColor/g, `fill:${accent}`);

        let link = document.querySelector('link[rel="icon"]');
        if (!link) {
            link = document.createElement("link");
            link.rel = "icon";
            document.head.appendChild(link);
        }

        link.type = "image/svg+xml";
        link.href = `data:image/svg+xml,${encodeURIComponent(svgText)}`;
    } catch (err) {
        console.warn("Could not update themed favicon:", err);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    applyStoredTheme();
    updateThemedFavicon();
});
