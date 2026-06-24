"""Theme ids — keep in sync with static/js/themes.js THEME_IDS."""

VALID_THEME_IDS = frozenset(
    {
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
    }
)

DEFAULT_THEME = "emerald"


def normalize_theme(theme_id):
    theme = (theme_id or "").strip().lower()
    return theme if theme in VALID_THEME_IDS else DEFAULT_THEME
