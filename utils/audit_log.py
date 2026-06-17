import json
import os
import re
from datetime import datetime, timezone

# Ensure LOG_DIR defaults to the root project's logs directory
LOG_DIR = os.getenv(
    "LOG_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"),
)

DEFAULT_LOG_LIMIT = 100
MAX_LOG_LIMIT = 500
_LOG_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TAIL_CHUNK_SIZE = 8192


def write_audit_log(action, user_email, target="", details=None):
    """Append a JSON line to logs/YYYY-MM-DD.log."""
    os.makedirs(LOG_DIR, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(LOG_DIR, f"{day}.log")
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": user_email or "system",
        "action": action,
        "target": target,
        "details": details or {},
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def normalize_log_limit(limit):
    """Clamp log query limits to a safe, bounded range."""
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = DEFAULT_LOG_LIMIT
    return max(1, min(value, MAX_LOG_LIMIT))


def validate_log_date(date_str):
    """Return a sanitized YYYY-MM-DD date string, or None if invalid."""
    if not date_str or not isinstance(date_str, str):
        return None
    date_str = os.path.basename(date_str.strip())
    if not _LOG_DATE_PATTERN.fullmatch(date_str):
        return None
    return date_str


def list_available_log_dates():
    """List available log dates (newest first) without reading file contents."""
    if not os.path.isdir(LOG_DIR):
        return []
    dates = [
        name[:-4]
        for name in os.listdir(LOG_DIR)
        if name.endswith(".log") and _LOG_DATE_PATTERN.fullmatch(name[:-4])
    ]
    return sorted(dates, reverse=True)


def resolve_log_file(date_str=None):
    """
    Resolve the log file path for a given date (or the newest available log).

    Returns (log_file, current_date). log_file is None when no logs exist.
    """
    available_dates = list_available_log_dates()
    if not available_dates:
        return None, ""

    if date_str:
        validated = validate_log_date(date_str)
        if not validated:
            raise ValueError("Invalid date format; expected YYYY-MM-DD")
        return os.path.join(LOG_DIR, f"{validated}.log"), validated

    current_date = available_dates[0]
    return os.path.join(LOG_DIR, f"{current_date}.log"), current_date


def read_recent_log_entries(path, limit=DEFAULT_LOG_LIMIT):
    """
    Read up to `limit` most recent JSON log entries from a file.

    Reads from the end of the file in chunks so large daily logs do not need
    to be fully loaded into memory.
    """
    limit = normalize_log_limit(limit)
    entries = []

    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            position = handle.tell()
            if position == 0:
                return []

            buffer = b""
            while position > 0 and len(entries) < limit:
                read_size = min(_TAIL_CHUNK_SIZE, position)
                position -= read_size
                handle.seek(position)
                buffer = handle.read(read_size) + buffer

                parts = buffer.split(b"\n")
                buffer = parts[0]

                for line in reversed(parts[1:]):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line.decode("utf-8")))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    if len(entries) >= limit:
                        return entries

            if len(entries) < limit and buffer.strip():
                try:
                    entries.append(json.loads(buffer.decode("utf-8")))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
    except OSError:
        return []

    return entries[:limit]
