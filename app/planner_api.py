from __future__ import annotations

import os
from datetime import timedelta

import httpx

from app.presentation import copy as phrases
from app.factors import LEVEL_RANK
from app.ingest import SourceRecord
from app.timeutil import as_utc, display, iso, utcnow

DEFAULT_PLANNER_API = "http://46.29.164.87:8000"
TIMEOUT = 40.0

GRADE_LEVEL = {
    "benign": "none",
    "elevated": "watch",
    "adverse": "warning",
    "insufficient_data": "unknown",
}

FACTOR_META = {
    "radiation_sep": {
        "key": "sep",
        "title": "Солнечные энергичные частицы",
        "mechanism": "sep",
        "limit": "Оценка удалённого API, не доза в скафандре",
    },
    "geomagnetic_activity": {
        "key": "geomagnetic",
        "title": "Геомагнитная обстановка (не суммируется с SEP)",
        "mechanism": "geomagnetic",
        "limit": "G не добавляется к SEP",
    },
    "mmod_meteoroid": {
        "key": "conjunction",
        "title": "MMOD / метеорная обстановка",
        "mechanism": "conjunction",
        "limit": "Не каталог SOCRATES; фактор MMOD удалённого API",
    },
}


def planner_base():
    return (os.environ.get("VKD_PLANNER_API") or DEFAULT_PLANNER_API).rstrip("/")


def _client():
    return httpx.Client(timeout=TIMEOUT, follow_redirects=True)


def fetch_data_sources_status():
    url = planner_base() + "/api/data-sources-status"
    with _client() as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def assess_window(window_start, duration_hours, as_of=None, **_ignored):
    """POST /api/assess-window — schema v0.2.0: window_start, duration_hours, as_of."""
    url = planner_base() + "/api/assess-window"
    payload = {
        "window_start": iso(window_start),
        "duration_hours": float(duration_hours),
    }
    if as_of is not None:
        payload["as_of"] = iso(as_of)
    with _client() as client:
        response = client.post(url, json=payload)
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail") or detail
            except Exception:
                pass
            raise RuntimeError("Планировщик {0}: {1}".format(response.status_code, detail))
        return response.json()


def planner_mode_for(req):
    if req["mode"] == "current":
        start = as_utc(req["start"])
        if start >= req["now"] - timedelta(hours=12):
            return "live"
    return "historical_review"


def planner_as_of(req, window_start):
    if planner_mode_for(req) == "live":
        return None
    cutoff = req.get("cutoff")
    window_start = as_utc(window_start)
    if cutoff is not None:
        cutoff = as_utc(cutoff)
        if cutoff > window_start:
            return window_start
        return cutoff
    return window_start


def level_from_grade(grade):
    return GRADE_LEVEL.get(grade or "", "unknown")


def _evidence(items):
    out = []
    for row in items or []:
        provenance = row.get("provenance") or row.get("provenance_type") or "external_forecast"
        kind = "observation" if provenance == "observation" else "external_forecast"
        sources = row.get("source_ids") or []
        if row.get("source_id"):
            sources = [row.get("source_id")] + list(sources)
        value = row.get("value")
        if value is None:
            value_text = row.get("statement") or "—"
        else:
            value_text = "{0} {1}".format(value, row.get("unit") or "").strip()
        out.append(
            phrases.evidence_item(
                {
                    "kind": kind,
                    "title": row.get("statement") or row.get("rule_id") or "свидетельство",
                    "value": value_text,
                    "detail": row.get("rule_description") or "",
                    "source_id": ", ".join([item for item in sources if item]) or "planner_api",
                    "time": row.get("timestamp"),
                    "rule": row.get("rule_id") or "",
                    "provenance": provenance,
                }
            )
        )
    return out


def factor_block(raw, fallback_key):
    factor_id = (raw or {}).get("factor_id") or fallback_key
    meta = FACTOR_META.get(factor_id) or {
        "key": fallback_key,
        "title": factor_id,
        "mechanism": fallback_key,
        "limit": "Удалённый API",
    }
    grade = (raw or {}).get("grade") or "insufficient_data"
    level = level_from_grade(grade)
    coverage = (raw or {}).get("coverage")
    return {
        "mechanism": meta["mechanism"],
        "title": meta["title"],
        "level": level,
        "grade": grade,
        "confidence": (raw or {}).get("confidence_reason") or (raw or {}).get("confidence") or "",
        "overlap_minutes": float((raw or {}).get("adverse_minutes") or 0),
        "incomplete": level == "unknown",
        "coverage": coverage,
        "evidence": _evidence((raw or {}).get("evidence")),
        "limitations": (raw or {}).get("limitations") or [],
        "applies_to": "окно ВКД",
        "limit": meta["limit"],
        "factor_id": factor_id,
    }


def window_from_assessment(raw, idx, duration_hours, is_requested=False):
    from datetime import datetime

    start = datetime.fromisoformat((raw.get("window_start") or "").replace("Z", "+00:00"))
    end = datetime.fromisoformat((raw.get("window_end") or "").replace("Z", "+00:00"))
    start = as_utc(start)
    end = as_utc(end)
    by_id = {}
    for item in raw.get("factors") or []:
        by_id[item.get("factor_id")] = item
    sep = factor_block(by_id.get("radiation_sep"), "radiation_sep")
    geo = factor_block(by_id.get("geomagnetic_activity"), "geomagnetic_activity")
    mmod = factor_block(by_id.get("mmod_meteoroid"), "mmod_meteoroid")
    cover_vals = [block.get("coverage") for block in (sep, geo, mmod) if block.get("coverage") is not None]
    cover = max(cover_vals) if cover_vals else 0.0
    if cover >= 0.8:
        tag = "ncei"
        labels = ["API"]
    elif cover > 0:
        tag = "donki"
        labels = ["API частично"]
    else:
        tag = "gap"
        labels = []
    critical_missing = sep["incomplete"]
    completeness = round(sum(1.0 if not block["incomplete"] else 0.0 for block in (sep, geo)) / 2.0, 2)
    adverse = 0.0
    if sep["level"] in ("warning", "high"):
        adverse += sep["overlap_minutes"]
    if mmod["level"] in ("warning", "high"):
        adverse += mmod["overlap_minutes"]
    worst = max(LEVEL_RANK.get(sep["level"], -1), LEVEL_RANK.get(mmod["level"], -1))
    orbit = raw.get("orbit_source") or {}
    traj = raw.get("trajectory_summary") or {}
    return {
        "id": "W{0}".format(idx + 1),
        "start": start,
        "end": end,
        "start_label": display(start),
        "end_label": display(end),
        "duration_hours": duration_hours,
        "day_label": start.strftime("%Y-%m-%d"),
        "sep": sep,
        "geomagnetic": geo,
        "conjunction": mmod,
        "radio": {
            "mechanism": "radio",
            "title": "Радиозатмения R",
            "level": "unknown",
            "incomplete": True,
            "evidence": [],
            "limit": "Нет отдельного фактора R в онлайн-API",
            "confidence": "",
        },
        "cme": {"count": 0, "earthward": 0, "fastest": None, "level": "unknown", "title": "CME", "evidence": [], "confidence": "", "limit": ""},
        "donki": {"count": 0, "types": "", "level": "unknown", "title": "DONKI", "evidence": [], "confidence": "", "limit": ""},
        "coverage": {"tag": tag, "labels": labels},
        "ap": None,
        "storm_prob": None,
        "track": {
            "shadow_percent": traj.get("shadow_percent"),
            "saa_percent": traj.get("saa_percent"),
            "mid": traj.get("mid") or {},
        } if traj else None,
        "orbit_raw": orbit,
        "critical_missing": critical_missing,
        "completeness": completeness,
        "completeness_note": phrases.window_completeness_note(
            {
                "completeness": completeness,
                "critical_missing": critical_missing,
                "sep": sep,
                "geomagnetic": geo,
                "conjunction": mmod,
            }
        ),
        "adverse_minutes": round(adverse, 1),
        "worst_rank": worst if worst >= 0 else 0,
        "is_requested": is_requested,
        "raw": raw,
    }


def status_sources(status):
    records = []
    records.append(
        SourceRecord(
            "planner_api",
            "ВКД-планировщик API",
            planner_base(),
            "catalog",
            ok=True,
            notes="онлайн {0}; overall={1}".format(
                planner_base(), (status or {}).get("overall_status")
            ),
            fetched_at=utcnow(),
        )
    )
    for row in (status or {}).get("sources") or []:
        records.append(
            SourceRecord(
                row.get("source_id") or "source",
                row.get("name") or row.get("source_id"),
                planner_base() + "/api/data-sources-status",
                "external_forecast",
                ok=row.get("status") == "available",
                error=None if row.get("status") == "available" else row.get("status"),
                notes="записей {0}; покрытие {1} — {2}".format(
                    row.get("record_count"),
                    row.get("coverage_start"),
                    row.get("coverage_end"),
                ),
                published_at=None,
                fetched_at=utcnow(),
            )
        )
    return records
