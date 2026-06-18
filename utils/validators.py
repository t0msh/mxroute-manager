import re

_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_LOCAL_PSEUDO_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+@[a-zA-Z0-9-]+$")

_PASSWORD_REQUIREMENTS = {
    "length": re.compile(r".{8,}"),
    "upper": re.compile(r"[A-Z]"),
    "lower": re.compile(r"[a-z]"),
    "number": re.compile(r"[0-9]"),
    "special": re.compile(r"[^A-Za-z0-9]"),
}


def validate_domain(domain):
    if not domain or not isinstance(domain, str):
        return False
    pattern = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
    return bool(re.match(pattern, domain))


def validate_username(username):
    if not username or not isinstance(username, str):
        return False
    pattern = r"^[a-zA-Z0-9._-]+$"
    return bool(re.match(pattern, username))


def validate_local_user_identifier(identifier):
    """Accept a local login name (e.g. billy), pseudo-email (e.g. user@local), or email address."""
    if not identifier or not isinstance(identifier, str):
        return False
    identifier = identifier.strip()
    if validate_username(identifier):
        return True
    if _EMAIL_PATTERN.fullmatch(identifier):
        return True
    return bool(_LOCAL_PSEUDO_EMAIL_PATTERN.fullmatch(identifier))


def is_email_identifier(identifier):
    if not identifier or not isinstance(identifier, str):
        return False
    return bool(_EMAIL_PATTERN.fullmatch(identifier.strip()))


def is_oidc_user_identifier(identifier, oidc_enabled):
    """True when the identifier is expected to authenticate through OIDC."""
    if not oidc_enabled:
        return False
    return is_email_identifier(identifier)


def requires_local_password(identifier, oidc_enabled):
    """True when the user authenticates locally and must have a password."""
    if not validate_local_user_identifier(identifier):
        return False
    return not is_oidc_user_identifier(identifier, oidc_enabled)


def validate_mailbox_password(password):
    if not password or not isinstance(password, str):
        return False
    return all(pattern.search(password) for pattern in _PASSWORD_REQUIREMENTS.values())


def validate_recovery_email(mailbox_email, recovery_email):
    """Validate recovery email for a mailbox. Returns (ok, error_message)."""
    mailbox_email = (mailbox_email or "").strip().lower()
    recovery_email = (recovery_email or "").strip().lower()
    if not recovery_email:
        return False, "Recovery email is required."
    if not is_email_identifier(recovery_email):
        return False, "Invalid recovery email format."
    if recovery_email == mailbox_email:
        return False, "Recovery email must differ from the mailbox address."
    return True, ""

