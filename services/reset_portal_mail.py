from email.utils import formataddr

from models.db import get_admin_notification_email
from services.mxroute import mx_request_raw
from utils.validators import nested_dict_get

RESET_SENDER_ALIAS = "reset"


def build_portal_reset_from_address(portal, domain):
    display = (portal.get("portal_title") or "").strip() or "Password Reset"
    email = f"{RESET_SENDER_ALIAS}@{domain.lower().strip()}"
    return formataddr((display, email))


def _forwarder_destinations(forwarder):
    destinations = forwarder.get("destinations")
    if destinations is None:
        forward_to = forwarder.get("forward_to")
        destinations = [forward_to] if forward_to else []
    return [
        destination.strip().lower()
        for destination in destinations
        if destination and str(destination).strip()
    ]


def _catch_all_satisfies_sender_verify(catch_all_data):
    if not isinstance(catch_all_data, dict):
        return False
    catch_type = (catch_all_data.get("type") or "").lower()
    if catch_type == "address":
        return bool((catch_all_data.get("address") or "").strip())
    if catch_type == "blackhole":
        return True
    return False


def _mx_error_message(response, fallback):
    if isinstance(response, dict):
        return nested_dict_get(response, "error", "message", default=fallback)
    return fallback


def ensure_reset_sender_forwarder(domain, admin_email=None, steps=None):
    """Ensure reset@{domain} exists on MXroute for branded reset email sender verify."""
    domain = (domain or "").lower().strip()
    admin_email = (admin_email or get_admin_notification_email() or "").strip().lower()
    if not admin_email:
        raise ValueError(
            "A contact email is required. Add one in Settings or Access Control "
            "(or sign in with an email-based login)."
        )

    if steps is None:
        steps = []

    catch_res, catch_status = mx_request_raw("GET", f"/domains/{domain}/catch-all")
    if catch_status == 200 and _catch_all_satisfies_sender_verify(
        catch_res.get("data")
    ):
        steps.append(
            f"Catch-all already configured for {domain}; "
            f"{RESET_SENDER_ALIAS}@{domain} sender verify satisfied (forwarder skipped)"
        )
        return "skipped"

    fwd_res, fwd_status = mx_request_raw("GET", f"/domains/{domain}/forwarders")
    if fwd_status != 200:
        raise ValueError(
            f"Failed to list forwarders for {domain}: "
            f"{_mx_error_message(fwd_res, 'Unknown error')}"
        )

    forwarders = fwd_res.get("data") or []
    existing = next(
        (
            forwarder
            for forwarder in forwarders
            if (forwarder.get("alias") or "").lower() == RESET_SENDER_ALIAS
        ),
        None,
    )

    outcome = "added"
    if existing:
        destinations = _forwarder_destinations(existing)
        if admin_email in destinations:
            steps.append(
                f"Forwarder {RESET_SENDER_ALIAS}@{domain} already forwards to admin contact (skipped)"
            )
            return "skipped"

        del_res, del_status = mx_request_raw(
            "DELETE",
            f"/domains/{domain}/forwarders/{RESET_SENDER_ALIAS}",
        )
        if del_status not in (200, 204):
            raise ValueError(
                f"Failed to remove existing {RESET_SENDER_ALIAS}@{domain} forwarder: "
                f"{_mx_error_message(del_res, 'Unknown error')}"
            )
        steps.append(
            f"Removed existing {RESET_SENDER_ALIAS}@{domain} forwarder to update destination"
        )
        outcome = "updated"

    post_res, post_status = mx_request_raw(
        "POST",
        f"/domains/{domain}/forwarders",
        {"alias": RESET_SENDER_ALIAS, "destinations": [admin_email]},
    )
    if post_status not in (200, 201, 204):
        raise ValueError(
            f"Failed to create {RESET_SENDER_ALIAS}@{domain} forwarder: "
            f"{_mx_error_message(post_res, 'Unknown error')}"
        )

    steps.append(f"Forwarder {RESET_SENDER_ALIAS}@{domain} → {admin_email} ({outcome})")
    return outcome
