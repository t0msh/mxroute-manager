import json
import os
from datetime import datetime, timezone

LOG_DIR = os.getenv(
    "LOG_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"),
)


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
