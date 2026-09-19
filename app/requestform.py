"""Parse the stand form into a calculation request."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.timeutil import HISTORICAL_END, HISTORICAL_START, MAX_INTERVAL_DAYS, parse_utc, utcnow


class RequestError(ValueError):
    pass


def _interval_days(form, start):
    raw = form.get("interval_days")
    if raw not in (None, ""):
        try:
            interval_days = int(float(raw))
        except (TypeError, ValueError):
            raise RequestError("Интервал задаётся целым числом суток")
    else:
        end_raw = (form.get("period_end_utc") or "").strip()
        if end_raw:
            period_end = parse_utc(end_raw)
            if period_end.hour == 0 and period_end.minute == 0 and period_end.second == 0 and start.hour != 0:
                period_end = period_end.replace(
                    hour=start.hour, minute=start.minute, second=start.second
                )
            if period_end < start:
                raise RequestError("Конец интервала не может быть раньше начала ВКД")
            interval_days = (period_end.date() - start.date()).days + 1
        else:
            interval_days = 1
    if interval_days < 1 or interval_days > MAX_INTERVAL_DAYS:
        raise RequestError("Интервал сравнения — от 1 до {0} суток".format(MAX_INTERVAL_DAYS))
    return interval_days


def parse_request(form):
    mode = (form.get("mode") or "current").strip()
    if mode not in ("current", "historical"):
        raise RequestError("Режим: current или historical")
    duration = float(form.get("duration_hours") or 6)
    search = float(form.get("search_hours") or 12)
    if duration < 1 or duration > 8:
        raise RequestError("Длительность ВКД должна быть от 1 до 8 часов")
    if search < 1 or search > 24:
        raise RequestError("Сдвиг внутри суток — от 1 до 24 часов")
    now = utcnow()
    start_raw = (form.get("start_utc") or "").strip()
    if start_raw:
        start = parse_utc(start_raw)
    elif mode == "current":
        start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        start = datetime(2024, 5, 11, 0, 0, tzinfo=timezone.utc)
    interval_days = _interval_days(form, start)
    period_end = start + timedelta(days=interval_days - 1)
    if mode == "historical":
        if start < HISTORICAL_START or start > HISTORICAL_END:
            raise RequestError("Исторический режим: дата в пределах 1 апреля — 31 июля 2024 UTC")
        if period_end > HISTORICAL_END:
            period_end = HISTORICAL_END
            interval_days = (period_end.date() - start.date()).days + 1
        if period_end < HISTORICAL_START:
            raise RequestError("Интервал выходит за пределы 1 апреля — 31 июля 2024 UTC")
    cutoff_raw = (form.get("cutoff_utc") or "").strip()
    if cutoff_raw:
        cutoff = parse_utc(cutoff_raw)
    elif mode == "current":
        cutoff = now
    else:
        cutoff = None
    refresh = str(form.get("refresh") or "") in ("1", "true", "on", "yes")
    freeze = str(form.get("freeze") or "") in ("1", "true", "on", "yes")
    previous_duration = form.get("previous_duration_hours")
    plan_change = False
    if previous_duration:
        try:
            plan_change = abs(float(previous_duration) - duration) > 1e-6
        except ValueError:
            plan_change = False
    return {
        "mode": mode,
        "start": start,
        "period_end": period_end,
        "interval_days": interval_days,
        "duration_hours": duration,
        "search_hours": search,
        "cutoff": cutoff,
        "refresh": refresh,
        "freeze": freeze,
        "plan_change": plan_change,
        "now": now,
    }
