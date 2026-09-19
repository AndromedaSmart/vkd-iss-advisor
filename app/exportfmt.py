from __future__ import annotations

import csv
import io

from app.timeutil import iso

CSV_COLUMNS = [
    "id",
    "day",
    "start",
    "end",
    "requested",
    "preferred",
    "coverage",
    "sep",
    "mmod",
    "geomagnetic",
    "donki",
    "cme",
    "adverse_minutes",
    "completeness",
    "critical_missing",
]


def _text(value):
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return iso(value)
    return str(value)


def _level(block):
    if not block:
        return ""
    if isinstance(block, dict):
        return block.get("level") or block.get("grade") or ""
    return str(block)


def window_csv_row(window):
    coverage = window.get("coverage") or {}
    labels = coverage.get("labels") or []
    if not labels and coverage.get("tag"):
        labels = [coverage.get("tag")]
    donki = window.get("donki") or {}
    cme = window.get("cme") or {}
    return {
        "id": window.get("id") or "",
        "day": window.get("day_label") or _text(window.get("start"))[:10],
        "start": _text(window.get("start")),
        "end": _text(window.get("end")),
        "requested": "1" if window.get("is_requested") or window.get("requested") else "0",
        "preferred": "1" if window.get("preferred") else "0",
        "coverage": ", ".join(labels) or coverage.get("tag") or "",
        "sep": _level(window.get("sep")),
        "mmod": _level(window.get("conjunction") or window.get("mmod")),
        "geomagnetic": _level(window.get("geomagnetic") or window.get("geo")),
        "donki": donki.get("count") if isinstance(donki, dict) else donki or 0,
        "cme": cme.get("count") if isinstance(cme, dict) else cme or 0,
        "adverse_minutes": window.get("adverse_minutes") if window.get("adverse_minutes") is not None else window.get("adverse") or 0,
        "completeness": window.get("completeness") if window.get("completeness") is not None else "",
        "critical_missing": "1" if window.get("critical_missing") or window.get("critical") else "0",
    }


def pack_to_csv(pack):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for window in pack.get("windows") or []:
        writer.writerow(window_csv_row(window))
    return buf.getvalue()
