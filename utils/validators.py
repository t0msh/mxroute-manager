import re


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
    """Accept a local login name (e.g. billy) or an email address (e.g. user@example.com)."""
    if not identifier or not isinstance(identifier, str):
        return False
    identifier = identifier.strip()
    if validate_username(identifier):
        return True
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(email_pattern, identifier))


def is_email_identifier(identifier):
    if not identifier or not isinstance(identifier, str):
        return False
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(email_pattern, identifier.strip()))


def requires_local_password(identifier, oidc_enabled):
    """True when the user authenticates locally and must have a password."""
    if not validate_local_user_identifier(identifier):
        return False
    if validate_username(identifier.strip()):
        return True
    return not oidc_enabled
