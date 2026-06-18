"""Bootstrap Icons markup helper for Jinja templates."""

from markupsafe import Markup


def icon(name: str, extra_class: str = "") -> Markup:
    """Return a Bootstrap Icons <i> element (self-hosted under /static/vendor/)."""
    cls = f"bi bi-{name}"
    if extra_class:
        cls += f" {extra_class}"
    return Markup(f'<i class="{cls}" aria-hidden="true"></i>')
