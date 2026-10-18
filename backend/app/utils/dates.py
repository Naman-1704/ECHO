from datetime import datetime, timezone


def to_naive_utc(dt: datetime | None) -> datetime | None:
    """
    SQLite DateTime columns drop tzinfo silently, which would store a header like
    '10:00 +0530' as 10:00 UTC. Normalising to naive UTC first keeps every stored date
    on one clock, so age calculations ('open for 21 days') are consistent.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
