"""Safe JSON API responses for Flask routes."""

import html

from flask import jsonify

GENERIC_ERROR = "The request could not be completed."
GENERIC_UPSTREAM_ERROR = "An upstream service error occurred."
INVALID_LOG_DATE_MESSAGE = "Invalid date format; expected YYYY-MM-DD"


def escape_client_text(value):
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def sanitize_client_json(value):
    if isinstance(value, str):
        return escape_client_text(value)
    if isinstance(value, dict):
        return {key: sanitize_client_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_client_json(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_client_json(item) for item in value)
    return value


def json_error(message, status=400):
    if not isinstance(message, str) or not message.strip():
        message = GENERIC_ERROR
    return jsonify(
        {"success": False, "error": {"message": escape_client_text(message)}}
    ), status


def json_ok(data=None, status=200, **extra):
    payload = {"success": True, **extra}
    if data is not None:
        payload["data"] = sanitize_client_json(data)
    return jsonify(payload), status


def mx_json_response(res, status):
    if status >= 500:
        return json_error(GENERIC_UPSTREAM_ERROR, status)
    if isinstance(res, dict):
        res = sanitize_client_json(res)
    return jsonify(res), status


def log_and_json_error(logger, message=GENERIC_ERROR, status=500):
    logger.exception(message)
    return json_error(message, status)


def client_value_error_message(exc, *, default=GENERIC_ERROR):
    if not isinstance(exc, ValueError) or not exc.args:
        return default
    msg = str(exc.args[0])
    if msg == INVALID_LOG_DATE_MESSAGE:
        return INVALID_LOG_DATE_MESSAGE
    if len(msg) <= 200 and "\n" not in msg:
        return escape_client_text(msg)
    return default
