from urllib.parse import quote


def field_text(fields, key, default=""):
    value = fields.get(key, default)
    return str(value or "").strip()


def field_bool(fields, key, default=False):
    value = fields.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes", "on")


def query_params(**pairs):
    parts = []
    for key, value in pairs.items():
        if value is None or value == "":
            continue
        parts.append(f"{quote(str(key), safe='')}={quote(str(value), safe='')}")
    return "&".join(parts)


def parse_header_fields(fields):
    headers = {}
    raw = field_text(fields, "auth_header")
    if raw:
        if ":" in raw:
            name, value = raw.split(":", 1)
            headers[name.strip()] = value.strip()
        else:
            headers["Authorization"] = f"Bearer {raw}"
    return headers
