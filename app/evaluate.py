from __future__ import annotations

import uuid
import os
from datetime import datetime, timedelta, timezone
from typing import List

from app import ALGORITHM_VERSION
from app.dataset import (
    cmes_for_window,
    coverage_for_day,
    dataset_status,
    load_geomag_forecast,
    notifications_for_window,
)
from app.factors import (
    apply_donki_to_sep,
    merge_geomag_product,
    score_cme,
    score_conjunctions,
    score_donki,
    score_geomagnetic,
    score_radio,
    score_sep,
)
from app.ingest import (
    SourceRecord,
    load_goes_protons,
    load_iss_tle,
    load_kp_now,
    load_noaa_scales,
    load_socrates,
    load_three_day_forecast,
)
from app.gp_history import gp_source_record, select_gp
from app.orbit import load_satrec, sample_track, sat_epoch
from app.planner_api import (
    assess_window,
    fetch_data_sources_status,
    planner_as_of,
    planner_base,
    planner_mode_for,
    status_sources,
    window_from_assessment,
)
from app.scoring import candidate_starts, compare_windows, worst_rank
from app.timeutil import (
    HISTORICAL_END,
    HISTORICAL_START,
    as_utc,
    display,
    iso,
    parse_utc,
    utcnow,
)

KIND_LABEL = {
    "observation": "наблюдение",
    "external_forecast": "внешний прогноз",
    "team_calc": "расчёт команды",
}


class RequestError(ValueError):
    pass


def _parse_interval_days(form, start):
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
    if interval_days < 1 or interval_days > 62:
        raise RequestError("Интервал сравнения — от 1 до 62 суток")
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
    interval_days = _parse_interval_days(form, start)
    period_end = start + timedelta(days=interval_days - 1)
    if mode == "historical":
        if start < HISTORICAL_START or start > HISTORICAL_END:
            raise RequestError("Исторический режим: дата в пределах 1 мая — 30 июня 2024 UTC")
        if period_end > HISTORICAL_END:
            period_end = HISTORICAL_END
            interval_days = (period_end.date() - start.date()).days + 1
        if period_end < HISTORICAL_START:
            raise RequestError("Интервал выходит за пределы 1 мая — 30 июня 2024 UTC")
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


def use_planner_api(form=None):
    form = form or {}
    if os.environ.get("VKD_LOCAL_ARCHIVES") in ("1", "true", "yes"):
        return False
    if str(form.get("offline") or "") in ("1", "true", "on", "yes"):
        return False
    return True


def evaluate(form):
    req = parse_request(form)
    if use_planner_api(form):
        return evaluate_via_planner(req)
    return evaluate_local(req)


def _planner_window_empty(window):
    """True when the remote assess-window result has no usable SEP/G coverage."""
    if window.get("critical_missing"):
        return True
    sep = window.get("sep") or {}
    if sep.get("incomplete") or sep.get("level") == "unknown":
        return True
    cover = (window.get("coverage") or {}).get("tag")
    if cover == "gap":
        return True
    try:
        coverage_value = float(sep.get("coverage") if sep.get("coverage") is not None else 0)
    except (TypeError, ValueError):
        coverage_value = 0.0
    return coverage_value <= 0 and cover not in ("ncei", "donki")


def _fill_empty_windows_from_local(req, windows):
    empty = [idx for idx, window in enumerate(windows) if _planner_window_empty(window)]
    if not empty:
        return windows, False, None
    local_pack = evaluate_local(req)
    by_day = {}
    for item in local_pack.get("windows") or []:
        key = item.get("day_label") or str(item.get("start") or "")[:10]
        by_day[key] = item
    filled = False
    out = list(windows)
    for idx in empty:
        window = out[idx]
        day = window.get("day_label") or str(window.get("start") or "")[:10]
        local = by_day.get(day)
        if not local:
            continue
        merged = dict(local)
        merged["id"] = window.get("id") or merged.get("id")
        merged["is_requested"] = window.get("is_requested")
        coverage = dict(merged.get("coverage") or {})
        labels = list(coverage.get("labels") or [])
        if "архив" not in labels:
            labels.insert(0, "архив")
        coverage["labels"] = labels
        merged["coverage"] = coverage
        merged["from_archive"] = True
        out[idx] = merged
        filled = True
    return out, filled, local_pack


def evaluate_via_planner(req):
    status = None
    try:
        status = fetch_data_sources_status()
    except Exception as exc:
        status = {"overall_status": "unavailable", "error": str(exc), "sources": []}
    sources = status_sources(status)
    duration = timedelta(hours=req["duration_hours"])
    starts = candidate_starts(
        req["start"], req["duration_hours"], req["search_hours"], period_end=req["period_end"]
    )
    api_mode = planner_mode_for(req)
    windows = []
    assessments = []
    last_error = None
    for idx, w_start in enumerate(starts):
        try:
            raw = assess_window(
                w_start,
                req["duration_hours"],
                as_of=planner_as_of(req, w_start),
            )
            assessments.append(raw)
            window = window_from_assessment(raw, idx, req["duration_hours"], is_requested=idx == 0)
            window["worst_rank"] = worst_rank([window["sep"]["level"], window["conjunction"]["level"]])
            windows.append(window)
        except Exception as exc:
            last_error = str(exc)
            w_end = w_start + duration
            windows.append(
                {
                    "id": "W{0}".format(idx + 1),
                    "start": w_start,
                    "end": w_end,
                    "start_label": display(w_start),
                    "end_label": display(w_end),
                    "duration_hours": req["duration_hours"],
                    "day_label": w_start.strftime("%Y-%m-%d"),
                    "sep": {
                        "mechanism": "sep",
                        "title": "Солнечные энергичные частицы",
                        "level": "unknown",
                        "incomplete": True,
                        "evidence": [],
                        "confidence": last_error,
                        "limit": "Онлайн-API недоступен для этого окна",
                        "overlap_minutes": 0,
                    },
                    "geomagnetic": {
                        "mechanism": "geomagnetic",
                        "title": "Геомагнитная обстановка",
                        "level": "unknown",
                        "incomplete": True,
                        "evidence": [],
                        "confidence": "",
                        "limit": "",
                    },
                    "conjunction": {
                        "mechanism": "conjunction",
                        "title": "MMOD",
                        "level": "unknown",
                        "incomplete": True,
                        "evidence": [],
                        "confidence": "",
                        "limit": "",
                    },
                    "radio": {"level": "unknown", "incomplete": True, "evidence": [], "title": "R", "confidence": "", "limit": ""},
                    "cme": {"count": 0, "earthward": 0, "level": "unknown", "title": "CME", "evidence": [], "confidence": "", "limit": ""},
                    "donki": {"count": 0, "types": "", "level": "unknown", "title": "DONKI", "evidence": [], "confidence": "", "limit": ""},
                    "coverage": {"tag": "gap", "labels": []},
                    "ap": None,
                    "storm_prob": None,
                    "track": None,
                    "critical_missing": True,
                    "completeness": 0.0,
                    "adverse_minutes": 0.0,
                    "worst_rank": 0,
                    "is_requested": idx == 0,
                }
            )
    orbit_meta = {
        "available": False,
        "role": "орбита приходит из онлайн-API вместе с оценкой окна",
        "warning": None,
    }
    if windows and windows[0].get("orbit_raw"):
        raw_orbit = windows[0]["orbit_raw"]
        orbit_meta = {
            "available": True,
            "source": raw_orbit.get("provider") or planner_base(),
            "epoch": raw_orbit.get("epoch"),
            "age_hours": raw_orbit.get("age_hours"),
            "role": "траектория из ВКД-планировщика API",
            "warning": "реконструкция" if raw_orbit.get("is_reconstruction") else None,
            "reconstruction": bool(raw_orbit.get("is_reconstruction")),
        }
    windows = [_public_window(w) for w in windows]
    windows, used_archive, local_pack = _fill_empty_windows_from_local(req, windows)
    if used_archive and local_pack and not orbit_meta.get("available"):
        orbit_meta = local_pack.get("orbit") or orbit_meta
    comparison = compare_windows(windows)
    for window in windows:
        window["preferred"] = comparison["preferred_id"] == window["id"]
        window["tied"] = window["id"] in comparison.get("tied_ids", [])
    notes = [
        "Онлайн-режим берёт данные с {0} (API v0.2.0): /api/assess-window и /api/data-sources-status.".format(planner_base()),
        "Факторы API: radiation_sep, geomagnetic_activity, mmod_meteoroid. Шкала G не суммируется с SEP.",
    ]
    if status and status.get("overall_status"):
        notes.append("Статус источников планировщика: {0}.".format(status.get("overall_status")))
    if last_error:
        notes.append("Часть окон не получена: {0}".format(last_error))
    if used_archive:
        notes.append(
            "Хост assess-window почти не пересекается с заявленным каталогом (кроме test_swpc на 2024-05-10 08:00 UTC). "
            "Пустые сутки заполнены локальным архивом NCEI/DONKI. Отсутствие файла ≠ all-clear."
        )
    if comparison["decision"] == "insufficient":
        notes.append(comparison["reason"])
    source_rows = [src.as_dict() for src in sources]
    if used_archive and local_pack:
        source_rows.extend(local_pack.get("sources") or [])
    dataset = {
        "root": planner_base(),
        "notifications": 0,
        "cmes": 0,
        "three_day_dirs": [],
        "overall_status": (status or {}).get("overall_status"),
    }
    if used_archive and local_pack and local_pack.get("dataset"):
        dataset = dict(local_pack["dataset"])
        dataset["overall_status"] = (status or {}).get("overall_status")
        dataset["planner_api"] = planner_base()
    pack = {
        "id": str(uuid.uuid4())[:8],
        "algorithm": ALGORITHM_VERSION,
        "generated_at": iso(req["now"]),
        "request": {
            "mode": req["mode"],
            "start": iso(req["start"]),
            "period_end": iso(req["period_end"]) if req["period_end"] else None,
            "interval_days": req["interval_days"],
            "duration_hours": req["duration_hours"],
            "search_hours": req["search_hours"],
            "cutoff": iso(req["cutoff"]),
            "timezone": "UTC",
            "freeze": req["freeze"],
            "refresh": req["refresh"],
            "plan_change": req["plan_change"],
            "planner_mode": api_mode,
            "planner_api": planner_base(),
        },
        "orbit": orbit_meta,
        "sources": source_rows,
        "windows": windows,
        "comparison": comparison,
        "notes": notes,
        "kind_label": KIND_LABEL,
        "ui": _ui(windows, req),
        "dataset": dataset,
    }
    return pack


def evaluate_local(req):
    sources = []  # type: List[SourceRecord]
    freeze = req["freeze"]
    refresh = req["refresh"]
    current = False

    def info_cap(moment):
        if req["cutoff"] is None:
            return moment
        return min(req["cutoff"], moment)

    forecast_cache = {}
    geomag_cache = {}

    def get_forecast(moment):
        cap_at = info_cap(moment)
        key = cap_at.strftime("%Y-%m-%dT%H:%M")
        if key not in forecast_cache:
            rec = load_three_day_forecast(cap_at, frozen=freeze, refresh=refresh, current=current)
            forecast_cache[key] = rec
            sources.append(rec)
        return forecast_cache[key]

    def get_geomag(moment):
        cap_at = info_cap(moment)
        key = cap_at.strftime("%Y-%m-%dT%H:%M")
        if key not in geomag_cache:
            rec = load_geomag_forecast(cap_at)
            geomag_cache[key] = rec
            sources.append(rec)
        return geomag_cache[key]

    sources.extend(_dataset_sources())

    protons = None
    kp_now = None
    scales = None
    if current:
        protons = load_goes_protons(frozen=freeze, refresh=refresh)
        sources.append(protons)
        kp_now = load_kp_now(frozen=freeze, refresh=refresh)
        sources.append(kp_now)
        scales = load_noaa_scales(frozen=freeze, refresh=refresh)
        sources.append(scales)
        if protons.ok and protons.published_at and req["cutoff"] and protons.published_at > req["cutoff"]:
            protons.payload = [row for row in protons.payload if row["time"] <= req["cutoff"]]
            protons.notes += "; отсечены точки после cutoff"

    tle = None
    sat = None
    historical_gp = None
    orbit_meta = {
        "available": False,
        "role": "не использовалась",
        "warning": None,
    }
    if current:
        tle = load_iss_tle(frozen=freeze, refresh=refresh)
        sources.append(tle)
        if tle.ok:
            sat = load_satrec(tle.payload["line1"], tle.payload["line2"])
            epoch = sat_epoch(sat)
            orbit_meta = {
                "available": True,
                "source": tle.name,
                "epoch": iso(epoch),
                "creation": None,
                "age_hours": round((req["now"] - epoch).total_seconds() / 3600.0, 2),
                "line1": tle.payload["line1"],
                "role": "траектория участвует в освещённости/SAA и проверке TCA относительно окна",
                "warning": None,
                "reconstruction": False,
                "frame": "SGP4 TEME → геодезические (приближённо)",
            }
    else:
        historical_gp = select_gp(req["start"], cutoff=info_cap(req["start"]))
        sources.append(gp_source_record(historical_gp))
        if historical_gp:
            sat = historical_gp["sat"]
            reconstruction = bool(historical_gp.get("reconstruction"))
            orbit_meta = {
                "available": True,
                "source": "Space-Track GP_HISTORY ISS 25544",
                "epoch": iso(historical_gp["epoch"]),
                "creation": iso(historical_gp["creation"]),
                "gp_id": historical_gp.get("gp_id"),
                "age_hours": round((req["start"] - historical_gp["epoch"]).total_seconds() / 3600.0, 2),
                "line1": historical_gp["line1"],
                "role": "историческая траектория по GP на дату окна: освещённость и SAA",
                "warning": (
                    "Геометрия — реконструкция: нет набора с CREATION_DATE ≤ отсечения. Отдельно от проверяемого прогноза SWPC."
                    if reconstruction
                    else None
                ),
                "reconstruction": reconstruction,
                "frame": "SGP4 TEME → геодезические (приближённо); CREATION_DATE ≠ EPOCH",
            }
        else:
            orbit_meta = {
                "available": False,
                "source": "Space-Track GP_HISTORY ISS 25544",
                "epoch": None,
                "role": "историческая орбита не подменяется текущим TLE",
                "warning": "В архиве GP_HISTORY нет элементов на этот интервал.",
                "reconstruction": False,
            }

    socrates = None
    conj_allowed = current
    if current:
        socrates = load_socrates(frozen=freeze, refresh=refresh)
        sources.append(socrates)
    else:
        sources.append(
            SourceRecord(
                "socrates",
                "CelesTrak SOCRATES Plus ISS",
                "не используется в replay",
                "external_forecast",
                ok=False,
                error="Текущий каталог сближений непригоден для исторического прогноза из прошлого",
                notes="Честный отказ, не all-clear",
            )
        )

    duration = timedelta(hours=req["duration_hours"])
    starts = candidate_starts(
        req["start"], req["duration_hours"], req["search_hours"], period_end=req["period_end"]
    )
    windows = []
    for idx, w_start in enumerate(starts):
        w_end = w_start + duration
        forecast = get_forecast(w_start)
        geomag = get_geomag(w_start) if not current else None
        cap_at = info_cap(w_start)
        sep = score_sep(w_start, w_end, forecast, protons, cap_at if not current else req["now"])
        geo = score_geomagnetic(w_start, w_end, forecast, kp_now if current else None)
        geo, ap_value, storm_prob = merge_geomag_product(geo, w_start, geomag)
        radio = score_radio(w_start, w_end, forecast)
        donki_hits = notifications_for_window(w_start, w_end, cap_at)
        cme_hits = cmes_for_window(w_start, w_end, cap_at)
        donki = score_donki(donki_hits)
        cme = score_cme(cme_hits)
        sep = apply_donki_to_sep(sep, donki)
        conj = score_conjunctions(w_start, w_end, socrates, allowed=conj_allowed)
        coverage = coverage_for_day(w_start, forecast.ok, donki_hits)
        track = None
        window_sat = sat
        if not current:
            window_gp = select_gp(w_start, cutoff=info_cap(w_start))
            window_sat = window_gp["sat"] if window_gp else None
        if window_sat is not None:
            track = sample_track(window_sat, w_start, w_end, step_minutes=10)
            sep["evidence"].append(
                {
                    "kind": "team_calc",
                    "title": "Пересечение воздействий с окном",
                    "value": "{0:.0f} мин неблагоприятного SEP-пересечения".format(sep["overlap_minutes"]),
                    "detail": "Освещённость: {0:.0f}% тени; SAA: {1:.0f}% точек трека. Это условие работ, не балл SEP.".format(
                        100 * track["shadow_fraction"], 100 * track["saa_fraction"]
                    ),
                    "source_id": "orbit",
                    "time": iso(w_start),
                    "rule": "SGP4, шаг 10 мин",
                }
            )
        if current:
            critical_missing = sep["incomplete"] or conj["incomplete"]
        else:
            critical_missing = sep["incomplete"]
        completeness = _completeness(sep, conj, forecast, current, coverage)
        adverse = 0.0
        if sep["level"] in ("warning", "high"):
            adverse += sep["overlap_minutes"]
        if conj["level"] in ("warning", "high"):
            adverse += conj["overlap_minutes"]
        windows.append(
            {
                "id": "W{0}".format(idx + 1),
                "start": w_start,
                "end": w_end,
                "start_label": display(w_start),
                "end_label": display(w_end),
                "duration_hours": req["duration_hours"],
                "day_label": w_start.strftime("%Y-%m-%d"),
                "sep": sep,
                "geomagnetic": geo,
                "conjunction": conj,
                "radio": radio,
                "cme": cme,
                "donki": donki,
                "coverage": coverage,
                "ap": ap_value,
                "storm_prob": storm_prob,
                "track": _compact_track(track),
                "critical_missing": critical_missing,
                "completeness": completeness,
                "adverse_minutes": round(adverse, 1),
                "worst_rank": worst_rank([sep["level"], conj["level"]]),
                "is_requested": idx == 0,
            }
        )

    comparison = compare_windows(windows)
    for window in windows:
        window["preferred"] = comparison["preferred_id"] == window["id"]
        window["tied"] = window["id"] in comparison.get("tied_ids", [])

    result_id = str(uuid.uuid4())[:8]
    pack = {
        "id": result_id,
        "algorithm": ALGORITHM_VERSION,
        "generated_at": iso(req["now"]),
        "request": {
            "mode": req["mode"],
            "start": iso(req["start"]),
            "period_end": iso(req["period_end"]) if req["period_end"] else None,
            "interval_days": req["interval_days"],
            "duration_hours": req["duration_hours"],
            "search_hours": req["search_hours"],
            "cutoff": iso(req["cutoff"]),
            "timezone": "UTC",
            "freeze": req["freeze"],
            "refresh": req["refresh"],
            "plan_change": req["plan_change"],
        },
        "orbit": orbit_meta,
        "sources": [src.as_dict() for src in sources],
        "windows": [_public_window(w) for w in windows],
        "comparison": comparison,
        "notes": _notes(req, list(forecast_cache.values()), windows, comparison),
        "kind_label": KIND_LABEL,
        "ui": _ui(windows, req),
        "dataset": dataset_status(),
    }
    return pack


def _completeness(sep, conj, forecast, current, coverage=None):
    parts = [
        1.0 if not sep["incomplete"] else 0.0,
        1.0 if forecast and forecast.ok else 0.0,
    ]
    if current:
        parts.append(1.0 if not conj["incomplete"] else 0.0)
    tag = (coverage or {}).get("tag")
    if tag == "gap":
        parts.append(0.0)
    elif tag == "donki":
        parts.append(0.5)
    elif tag:
        parts.append(1.0)
    return round(sum(parts) / float(len(parts)), 2)


def _dataset_sources():
    status = dataset_status()
    records = []
    if status["root"]:
        records.append(
            SourceRecord(
                "local_bundle",
                "Локальный набор data/",
                status["root"],
                "catalog",
                ok=True,
                notes="3-day dirs: {0}; DONKI {1}; CME {2}".format(
                    ", ".join(status["three_day_dirs"]),
                    status["notifications"],
                    status["cmes"],
                ),
            )
        )
    if status["notifications"]:
        records.append(
            SourceRecord(
                "donki_notifications",
                "NASA DONKI notifications",
                status["root"] + "/notifications_may_june.json",
                "external_forecast",
                ok=True,
                notes="{0} сообщений May–June 2024; replay по messageIssueTime".format(
                    status["notifications"]
                ),
            )
        )
    if status["cmes"]:
        records.append(
            SourceRecord(
                "donki_cme",
                "NASA DONKI CME analysis",
                status["root"] + "/cme_analysis_may_june.json",
                "external_forecast",
                ok=True,
                notes="{0} записей; earthward по lon/halfAngle; submissionTime для replay".format(
                    status["cmes"]
                ),
            )
        )
    return records


def _ui(windows, req):
    cols = [
        {"id": "day", "title": "День"},
        {"id": "window", "title": "Окно"},
        {"id": "interval", "title": "Интервал UTC"},
    ]
    tags = set((w.get("coverage") or {}).get("tag") for w in windows)
    if tags - {None}:
        cols.append({"id": "coverage", "title": "Покрытие"})
    cols.append({"id": "sep", "title": "SEP"})
    if any((w.get("radio") or {}).get("level") not in (None, "unknown") for w in windows):
        cols.append({"id": "radio", "title": "R"})
    if any((w.get("cme") or {}).get("count") for w in windows):
        cols.append({"id": "cme", "title": "CME"})
    if any((w.get("donki") or {}).get("count") for w in windows):
        cols.append({"id": "donki", "title": "DONKI"})
    if req["mode"] == "current" or any(w["conjunction"]["level"] != "unknown" for w in windows):
        cols.append({"id": "conj", "title": "Сближения"})
    cols.append({"id": "geo", "title": "G (отдельно)"})
    if any(w.get("ap") is not None for w in windows):
        cols.append({"id": "ap", "title": "Ap"})
    if any(w.get("storm_prob") is not None for w in windows):
        cols.append({"id": "storm", "title": "G3+"})
    cols.extend(
        [
            {"id": "adverse", "title": "Неблагопр., мин"},
            {"id": "completeness", "title": "Полнота"},
        ]
    )
    evidence = ["sep"]
    if req["mode"] == "current":
        evidence.append("conjunction")
    evidence.append("geomagnetic")
    if any((w.get("radio") or {}).get("level") not in (None, "unknown") for w in windows):
        evidence.append("radio")
    if any((w.get("cme") or {}).get("count") for w in windows):
        evidence.append("cme")
    if any((w.get("donki") or {}).get("count") for w in windows):
        evidence.append("donki")
    gap_days = [w["day_label"] for w in windows if (w.get("coverage") or {}).get("tag") == "gap"]
    donki_days = [w["day_label"] for w in windows if (w.get("coverage") or {}).get("tag") == "donki"]
    return {
        "columns": cols,
        "evidence": evidence,
        "gap_days": gap_days,
        "donki_only_days": donki_days,
    }


def _compact_track(track):
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


def _public_window(window):
    out = dict(window)
    out.pop("raw", None)
    out.pop("orbit_raw", None)
    out["start"] = iso(window["start"])
    out["end"] = iso(window["end"])
    if out.get("track") and out["track"].get("points"):
        points = []
        for pt in out["track"]["points"]:
            item = dict(pt)
            item["time"] = iso(pt["time"])
            points.append(item)
        out["track"] = dict(out["track"])
        out["track"]["points"] = points
        for key in ("first", "mid", "last"):
            item = dict(out["track"][key])
            item["time"] = iso(out["track"][key]["time"])
            out["track"][key] = item
    return out


def _notes(req, forecasts, windows, comparison):
    notes = [
        "Сервис — исследовательский прототип поддержки решений, не допуск к ВКД.",
        "Механизм 1: SEP. Механизм 2: сближения каталожных объектов. Шкала G показывается отдельно и не прибавляется к SEP.",
    ]
    if req.get("interval_days", 1) > 1:
        notes.append(
            "Интервал сравнения: {0} сут ({1} — {2}), одно окно {3} ч на каждые сутки.".format(
                req["interval_days"],
                req["start"].strftime("%Y-%m-%d"),
                req["period_end"].strftime("%Y-%m-%d"),
                req["duration_hours"],
            )
        )
    if req["mode"] == "historical":
        cap = iso(req["cutoff"]) if req["cutoff"] else "начала каждого окна"
        notes.append(
            "Исторический режим: 3-day forecast и GP ISS с временем публикации ≤ {0}. SOCRATES и современный TLE не используются.".format(
                cap
            )
        )
    if req["plan_change"]:
        notes.append("Изменение длительности показано как изменение плана, не как улучшение при прежних условиях.")
    issued = []
    seen = set()
    for rec in forecasts or []:
        stamp = iso(rec.published_at) if rec and rec.ok else None
        if stamp and stamp not in seen:
            seen.add(stamp)
            issued.append(stamp)
    if issued:
        notes.append("Выпуски SWPC 3-Day Forecast: {0}.".format(", ".join(issued)))
    status = dataset_status()
    if status["root"]:
        notes.append(
            "Локальный набор {0}: 3-day/geomag NCEI, DONKI {1}, CME {2}.".format(
                status["root"], status["notifications"], status["cmes"]
            )
        )
    gap = [w["day_label"] for w in windows if (w.get("coverage") or {}).get("tag") == "gap"]
    if gap:
        notes.append("Дыры покрытия NCEI/DONKI в сутках: {0}. Отсутствие файла ≠ all-clear.".format(", ".join(gap)))
    if comparison["decision"] == "insufficient":
        notes.append(comparison["reason"])
    return notes


def json_ready(pack):
    return pack
