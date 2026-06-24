/** Theme ids and labels — keep in sync with body.theme-* rules in style.css */

export const THEME_IDS = [
    "emerald",
    "indigo",
    "crimson",
    "amber",
    "amethyst",
    "cyberpunk",
    "rainbow",
    "emerald-light",
    "indigo-light",
    "slate-light",
    "rose-light",
    "rainbow-light",
];

export const THEME_META = {
    emerald: { label: "Emerald Glass", accent: "#5cdd8d", mode: "dark" },
    indigo: { label: "Classic Indigo", accent: "#6366f1", mode: "dark" },
    crimson: { label: "Crimson Dusk", accent: "#f43f5e", mode: "dark" },
    amber: { label: "Amber Sunset", accent: "#f59e0b", mode: "dark" },
    amethyst: { label: "Amethyst Glow", accent: "#a855f7", mode: "dark" },
    cyberpunk: { label: "Cyberpunk", accent: "#00f0ff", mode: "dark" },
    rainbow: { label: "Unicorn Puke", accent: "#ff6ec7", mode: "dark" },
    "emerald-light": { label: "Mint Paper", accent: "#059669", mode: "light" },
    "indigo-light": { label: "Indigo Day", accent: "#4f46e5", mode: "light" },
    "slate-light": { label: "Slate Office", accent: "#475569", mode: "light" },
    "rose-light": { label: "Rose Blush", accent: "#e11d48", mode: "light" },
    "rainbow-light": { label: "Cotton Candy", accent: "#e879f9", mode: "light" },
};

export function isLightTheme(themeId) {
    return THEME_META[themeId]?.mode === "light";
}
