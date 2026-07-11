import datetime as dt


def utcnow() -> dt.datetime:
    """Return the current moment as a timezone-aware UTC datetime."""
    return dt.datetime.now(dt.UTC)
