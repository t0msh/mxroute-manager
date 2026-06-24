from flask import current_app, jsonify, request

from models.db import get_notification_settings, save_notification_settings
from routes.admin_blueprint import admin_bp
from services.mail import is_smtp_configured, smtp_config_from_settings
from services.mxroute import audit
from services.notifications import (
    is_notification_configured,
    mask_notification_settings_for_response,
    resolve_apprise_urls,
    send_test_notification,
)
from utils.apprise_builder import (
    builder_catalog_for_api,
    compile_service_url,
    cred_env_keys_for_api,
    parse_service_url,
    resolve_target_url,
    service_label_from_url,
    validate_apprise_url,
)
from utils.audit_actions import (
    DESTRUCTIVE_ACTION_IDS,
    audit_action_ids,
    grouped_audit_actions,
)
from utils.auth_helpers import get_current_user, require_admin


def merge_target_urls(incoming_targets, existing_targets):
    """Preserve stored URLs and cred_env when the client sends masked placeholders."""
    existing_by_label = {}
    for index, target in enumerate(existing_targets or []):
        label = str((target or {}).get("label") or "").strip()
        key = label or f"__index_{index}"
        existing_by_label[key] = target or {}

    merged = []
    for index, target in enumerate(incoming_targets or []):
        if not isinstance(target, dict):
            continue
        label = str(target.get("label") or "").strip()
        url = str(target.get("url") or "").strip()
        key = label or f"__index_{index}"
        existing = existing_by_label.get(key, {})
        if not url or "***" in url:
            url = str(existing.get("url") or "").strip()
        cred_env = (
            str(target.get("cred_env") or existing.get("cred_env") or "").strip()
            or None
        )
        if not url:
            continue
        service_id = str(
            target.get("service_id")
            or target.get("service")
            or existing.get("service_id")
            or ""
        ).strip()
        merged.append(
            {
                "label": label,
                "url": url,
                "service": str(target.get("service") or service_label_from_url(url)),
                "service_id": service_id or service_label_from_url(url),
                "cred_env": cred_env,
            }
        )
    return merged


def normalize_notification_payload(data):
    existing = get_notification_settings()
    enabled = bool(data.get("enabled"))
    actions = data.get("actions") if isinstance(data.get("actions"), list) else []
    actions = [
        str(action).strip()
        for action in actions
        if str(action).strip() in audit_action_ids()
    ]

    targets = merge_target_urls(data.get("targets"), existing.get("targets"))
    for target in targets:
        deliverable = resolve_target_url(target)
        if not deliverable:
            raise ValueError(
                f'Target "{target.get("label") or "unnamed"}" is missing a URL'
            )
        validate_apprise_url(deliverable)

    if enabled:
        if not actions:
            raise ValueError("Select at least one audit event to notify on")
        if not targets:
            raise ValueError("Add at least one notification target")

    monitor_raw = (
        data.get("dns_monitor") if isinstance(data.get("dns_monitor"), dict) else {}
    )
    if not monitor_raw and isinstance(existing.get("dns_monitor"), dict):
        monitor_raw = existing.get("dns_monitor")
    monitor_enabled = bool(monitor_raw.get("enabled"))
    try:
        interval_hours = int(monitor_raw.get("interval_hours", 24))
    except (TypeError, ValueError):
        interval_hours = 24
    interval_hours = max(1, min(168, interval_hours))

    if monitor_enabled:
        for action_id in ("dns.health_alert", "dns.health_recovered"):
            if action_id not in actions:
                actions.append(action_id)

    return {
        "enabled": enabled,
        "targets": targets,
        "actions": actions,
        "dns_monitor": {
            "enabled": monitor_enabled,
            "interval_hours": interval_hours,
        },
    }


def resolve_apprise_urls_for_test():
    return bool(resolve_apprise_urls())


@admin_bp.route("/api/admin/notifications", methods=["GET"])
@require_admin
def get_notifications():
    config = get_notification_settings()
    data = mask_notification_settings_for_response(config)
    data["destructive_action_ids"] = sorted(DESTRUCTIVE_ACTION_IDS)
    data["configured"] = is_notification_configured()
    return jsonify({"success": True, "data": data})


@admin_bp.route("/api/admin/notifications", methods=["POST"])
@require_admin
def save_notifications():
    data = request.json or {}
    try:
        normalized = normalize_notification_payload(data)
        save_notification_settings(normalized)
        audit("settings.update", target="notifications", keys=["NOTIFICATION_SETTINGS"])
        return jsonify(
            {
                "success": True,
                "data": mask_notification_settings_for_response(normalized),
            }
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": {"message": str(exc)}}), 400
    except Exception as exc:
        current_app.logger.error(f"Error saving notification settings: {exc}")
        return jsonify(
            {
                "success": False,
                "error": {"message": "Failed to save notification settings."},
            }
        ), 500


@admin_bp.route("/api/admin/notifications/actions", methods=["GET"])
@require_admin
def get_notification_actions():
    return jsonify(
        {
            "success": True,
            "data": {
                "groups": grouped_audit_actions(),
                "destructive_action_ids": sorted(DESTRUCTIVE_ACTION_IDS),
            },
        }
    )


@admin_bp.route("/api/admin/notifications/builder", methods=["GET"])
@require_admin
def get_notification_builder():
    return jsonify(
        {
            "success": True,
            "data": {
                "services": builder_catalog_for_api(),
                "cred_env_map": cred_env_keys_for_api(),
                "reset_smtp_configured": is_smtp_configured(
                    smtp_config_from_settings()
                ),
            },
        }
    )


@admin_bp.route("/api/admin/notifications/builder/parse", methods=["POST"])
@require_admin
def parse_notification_url():
    data = request.json or {}
    url = str(data.get("url") or "").strip()
    service_id = str(data.get("service_id") or "").strip()
    cred_env = str(data.get("cred_env") or "").strip() or None

    target_index = data.get("target_index")
    if target_index is not None:
        try:
            idx = int(target_index)
        except (TypeError, ValueError):
            return jsonify(
                {"success": False, "error": {"message": "Invalid target index."}}
            ), 400
        config = get_notification_settings()
        targets = config.get("targets") or []
        if not (0 <= idx < len(targets)):
            return jsonify(
                {"success": False, "error": {"message": "Target not found."}}
            ), 400
        stored = targets[idx]
        url = str(stored.get("url") or "").strip()
        service_id = str(
            stored.get("service_id") or stored.get("service") or service_id
        ).strip()
        cred_env = str(stored.get("cred_env") or "").strip() or None

    try:
        parsed = parse_service_url(service_id, url, cred_env=cred_env)
        return jsonify({"success": True, "data": parsed})
    except ValueError as exc:
        return jsonify({"success": False, "error": {"message": str(exc)}}), 400


@admin_bp.route("/api/admin/notifications/builder/compile", methods=["POST"])
@require_admin
def compile_notification_url():
    data = request.json or {}
    service_id = str(data.get("service_id") or "").strip()
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    token_in_env = bool(data.get("token_in_env"))
    try:
        compiled = compile_service_url(service_id, fields, token_in_env=token_in_env)
        return jsonify({"success": True, "data": compiled})
    except ValueError as exc:
        return jsonify({"success": False, "error": {"message": str(exc)}}), 400


@admin_bp.route("/api/admin/notifications/test", methods=["POST"])
@require_admin
def test_notifications():
    if not resolve_apprise_urls_for_test():
        return jsonify(
            {
                "success": False,
                "error": {
                    "message": "No notification targets configured. Add a target first."
                },
            }
        ), 400
    try:
        send_test_notification()
        current_user = get_current_user()
        login_identifier = (current_user or {}).get(
            "email", ""
        ).strip().lower() or "admin"
        audit("notification.test", target=login_identifier)
        return jsonify({"success": True, "message": "Test notification sent."})
    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "error": {"message": f"Failed to send test notification: {exc}"},
            }
        ), 500
