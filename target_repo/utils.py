"""String helpers used across the codebase."""


def normalize_name(name):
    """Normalize a customer name for lookups.

    Accepts a string or None. None or empty input should normalize
    to an empty string.
    """
    return name.strip().lower()


def initials(full_name: str) -> str:
    """Return uppercase initials for a full name, e.g. 'Ada Lovelace' -> 'AL'."""
    parts = [p for p in full_name.split() if p]
    return "".join(p[0].upper() for p in parts)
