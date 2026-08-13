"""Small shared helpers for the web and API layers."""

from __future__ import annotations

from datetime import datetime

_TIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def parse_utc_datetime(value) -> datetime:
    """Parse a UTC timestamp from ISO-ish strings (HTML ``datetime-local``
    inputs included).  Raises ``ValueError`` on failure."""
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    # Tolerate an explicit UTC suffix and fractional seconds.
    if text.endswith("Z"):
        text = text[:-1]
    if "." in text:
        text = text.split(".", 1)[0]
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError("Could not parse timestamp %r (expected ISO 8601 UTC)" % value)


def format_duration(seconds: float) -> str:
    """Human-readable duration, e.g. ``2h 05m`` or ``38m 12s``."""
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return "%dh %02dm" % (hours, minutes)
    if minutes:
        return "%dm %02ds" % (minutes, secs)
    return "%ds" % secs
