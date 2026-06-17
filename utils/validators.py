import re

_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_LOCAL_PSEUDO_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+@[a-zA-Z0-9-]+$")


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
