from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.factors import LEVEL_RANK
from app.timeutil import as_utc


def _unique(starts):
    uniq = []
    seen = set()
    for item in starts:
        key = item.isoformat()
        if key not in seen:
            seen.add(key)
            uniq.append(item)
    return uniq


def candidate_starts(start, duration_hours, search_hours, period_end=None):
    """Equal-duration candidate EVA starts.

    If period_end falls on a later UTC date than start, one window per day
    at the same clock time. Otherwise keep intra-day shifts within search_hours.
    """
    start = as_utc(start)
    if period_end is not None:
        period_end = as_utc(period_end)
        last_day = period_end.date()
        first_day = start.date()
        if last_day > first_day:
            starts = []
            day = first_day
            while day <= last_day:
                day_start = datetime(
                    day.year,
                    day.month,
                    day.day,
                    start.hour,
                    start.minute,
                    start.second,
                    tzinfo=timezone.utc,
                )
                starts.append(day_start)
                day = day + timedelta(days=1)
            return _unique(starts)

    starts = [start]
    step = timedelta(hours=3)
    if search_hours <= 3:
        step = timedelta(hours=1)
    cursor = start + step
    last = start + timedelta(hours=search_hours)
    while cursor <= last:
        starts.append(cursor)
        cursor += step
    if len(starts) == 1:
        extra = start + timedelta(hours=min(float(search_hours), 3.0))
        if extra != start:
            starts.append(extra)
    return _unique(starts)


def compare_windows(windows):
    usable = [w for w in windows if not w["critical_missing"]]
    if not usable:
        return {
            "decision": "insufficient",
            "preferred_id": None,
            "reason": "Недостаточно данных по критичному механизму хотя бы для одного окна. Это не спокойная обстановка.",
            "tied_ids": [],
        }

    def key(window):
        return (
            window["worst_rank"],
            window["adverse_minutes"],
            -window["completeness"],
        )

    ordered = sorted(usable, key=key)
    best = ordered[0]
    tied = [w for w in ordered if key(w) == key(best)]
    if len(tied) > 1:
        return {
            "decision": "equivalent",
            "preferred_id": None,
            "tied_ids": [w["id"] for w in tied],
            "reason": "Окна одинаковой длительности не различаются по худшему уровню и длительности неблагоприятного пересечения. Победитель не назначается.",
        }
    return {
        "decision": "prefer",
        "preferred_id": best["id"],
        "tied_ids": [],
        "reason": "Меньше пересечения с уровнем warning+ при сопоставимой полноте. Связанные сигналы SEP не суммировались со шкалой G.",
    }


def worst_rank(levels):
    ranks = [LEVEL_RANK.get(level, 0) for level in levels if level != "unknown"]
    return max(ranks) if ranks else 0
