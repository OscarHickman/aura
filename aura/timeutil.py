"""Time helpers.

`datetime.utcnow()` is deprecated from Python 3.12 and scheduled for removal.
`utcnow()` here is a drop-in replacement that keeps the exact same semantics
(a *naive* datetime in UTC) so existing ISO timestamps stored in the database
remain byte-identical and string comparisons keep working.
"""

from datetime import datetime, timezone

__all__ = ["utcnow", "utcnow_iso"]


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime (no tzinfo)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return utcnow().isoformat()
