"""Danger timeline over a request interval. Scoring rules stay in factors."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.factors import level_from_g, level_from_s, s_scale_from_flux
from app.timeutil import iso


def interval_range(req):
    start = req["start"].replace(hour=0, minute=0, second=0, microsecond=0)
    last = (req.get("period_end") or req["start"]).replace(hour=0, minute=0, second=0, microsecond=0)
    if last < start:
        last = start
    return start, last + timedelta(days=1)


def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and len(value) >= 10:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def window_level_at(windows, moment, name):
    day = as_date(moment)
    if day is None:
        return None
    for window in windows or []:
        if as_date(window.get("start")) != day:
            continue
        block = window.get(name) or {}
        if isinstance(block, dict):
            return block.get("level")
        return None
    return None


def merge_forecasts(forecasts):
    bins = []
    for rec in forecasts or []:
        if rec and getattr(rec, "ok", False) and rec.payload:
            bins.extend(rec.payload.get("kp_bins") or [])
    return type("ForecastView", (), {"ok": True, "payload": {"kp_bins": bins}})()


def merge_conjunctions(windows):
    events = []
    incomplete = True
    for window in windows or []:
        conj = window.get("conjunction") or {}
        events.extend(conj.get("events") or [])
        if not conj.get("incomplete"):
            incomplete = False
    return {"events": events, "incomplete": incomplete, "level": "unknown"}


def conjunction_event_level(event):
    rng = event.get("min_range_km")
    if rng is None:
        return "unknown"
    if rng < 1.0:
        return "high"
    if rng < 2.0:
        return "warning"
    if rng < 5.0:
        return "watch"
    return "none"


def danger_timeline(
    day_start,
    day_end,
    protons,
    forecast,
    sep_level,
    geo_level,
    conj,
    window_start=None,
    window_end=None,
    windows=None,
):
    span_min = max(1, int((day_end - day_start).total_seconds() / 60.0))
    if span_min <= 180:
        step = 10
    elif span_min <= 12 * 60:
        step = 15
    elif span_min <= 36 * 60:
        step = 30
    else:
        step = 60
    proton_rows = []
    if protons and protons.ok and protons.payload:
        proton_rows = [row for row in protons.payload if day_start <= row["time"] <= day_end]
    bins = []
    if forecast and forecast.ok and forecast.payload:
        bins = forecast.payload.get("kp_bins") or []
    events = (conj or {}).get("events") or []
    conj_incomplete = bool((conj or {}).get("incomplete"))
    rank = {"none": 0, "watch": 1, "warning": 2, "high": 3}

    def in_window(moment):
        if window_start is None or window_end is None:
            return True
        return window_start <= moment <= window_end

    points = []
    cursor = day_start
    last_sep = None
    while cursor <= day_end:
        nxt = min(cursor + timedelta(minutes=step), day_end)
        chunk = [row for row in proton_rows if cursor <= row["time"] <= nxt]
        if chunk:
            flux = max(row["flux"] for row in chunk)
            sep = level_from_s(s_scale_from_flux(flux))
            last_sep = sep
        elif last_sep is not None:
            sep = last_sep
        else:
            sep = (
                window_level_at(windows, cursor, "sep")
                or (sep_level if in_window(cursor) else None)
                or "unknown"
            )
        geo = "unknown"
        for item in bins:
            if item["start"] <= cursor <= item["end"]:
                geo = level_from_g(item.get("g"))
                break
        if geo == "unknown":
            geo = (
                window_level_at(windows, cursor, "geomagnetic")
                or (geo_level if in_window(cursor) else None)
                or "unknown"
            )
        if conj_incomplete:
            mmod = "unknown"
        else:
            mmod = "none"
            for event in events:
                tca = event.get("tca")
                if tca is None:
                    continue
                if abs((tca - cursor).total_seconds()) <= 30 * 60:
                    other = conjunction_event_level(event)
                    if other == "unknown":
                        continue
                    if rank.get(other, 0) > rank.get(mmod, 0):
                        mmod = other
        points.append({"t": iso(cursor), "sep": sep, "mmod": mmod, "geo": geo})
        if cursor >= day_end:
            break
        cursor = nxt
    if not points:
        fallback_mmod = (conj or {}).get("level") or "unknown"
        points = [
            {"t": iso(day_start), "sep": sep_level, "mmod": fallback_mmod, "geo": geo_level},
            {"t": iso(day_end), "sep": sep_level, "mmod": fallback_mmod, "geo": geo_level},
        ]
    return points


def compact_track(track):
    if not track:
        return None
    pts = track["points"]
    mid = pts[len(pts) // 2]
    return {
        "n_points": len(pts),
        "first": pts[0],
        "mid": mid,
        "last": pts[-1],
        "shadow_percent": round(100 * track["shadow_fraction"], 1),
        "saa_percent": round(100 * track["saa_fraction"], 1),
        "sunlit_percent": round(100 * track["sunlit_fraction"], 1),
        "points": pts,
    }
