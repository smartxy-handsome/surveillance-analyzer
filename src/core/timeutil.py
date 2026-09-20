"""Shared time helpers."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Naive UTC timestamp, replacing the deprecated ``datetime.utcnow()``.

    Keeps the naive (timezone-unaware) semantics the database columns were
    built on, so values stored before and after this change stay comparable.
    """
    return datetime.now(UTC).replace(tzinfo=None)
