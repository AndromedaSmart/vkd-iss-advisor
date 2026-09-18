from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from dateutil import parser as date_parser

MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

HISTORICAL_START = datetime(2024, 5, 1, tzinfo=timezone.utc)
HISTORICAL_END = datetime(2024, 6, 30, 23, 59, 59, tzinfo=timezone.utc)


def utcnow():
    return datetime.now(timezone.utc)


def as_utc(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_utc(text):
    # type: (str) -> datetime
    text = (text or "").strip()
    if not text:
        raise ValueError("Пустая отметка времени")
    dt = date_parser.parse(text, yearfirst=True, dayfirst=False)
    return as_utc(dt)


def parse_issued_swpc(text):
    # type: (str) -> Optional[datetime]
    """Parse ':Issued: 2024 May 10 1230 UTC' without depending on locale."""
    marker = ":Issued:"
    if marker not in text:
        return None
    rest = text.split(marker, 1)[1].splitlines()[0].strip()
    rest = rest.replace("UTC", "").strip()
    parts = rest.split()
    if len(parts) < 4:
        return None
    year = int(parts[0])
    month = MONTHS.get(parts[1][:3])
    day = int(parts[2])
    hhmm = parts[3]
    if month is None or len(hhmm) not in (3, 4):
        return None
    hhmm = hhmm.zfill(4)
    return datetime(year, month, day, int(hhmm[:2]), int(hhmm[2:]), tzinfo=timezone.utc)


def iso(dt):
    if dt is None:
        return None
    return as_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def display(dt):
    if dt is None:
        return "—"
    return as_utc(dt).strftime("%Y-%m-%d %H:%M UTC")


def overlap_minutes(a0, a1, b0, b1):
    start = max(a0, b0)
    end = min(a1, b1)
    if end <= start:
        return 0.0
    return (end - start).total_seconds() / 60.0


def iter_steps(start, end, step):
    # type: (datetime, datetime, timedelta) -> list
    points = []
    t = start
    while t <= end:
        points.append(t)
        t = t + step
    if not points or points[-1] != end:
        points.append(end)
    return points
