from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.ingest import SourceRecord
from app.orbit import load_satrec
from app.timeutil import as_utc, iso

GP_HISTORY_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "archive" / "iss_gp_history_2024.json"
)

_CACHE = None


def parse_space_track_time(text):
    if not text:
        return None
    return as_utc(datetime.fromisoformat(text))


def resolve_gp_history_path(path=None):
    if path:
        return Path(path)
    from app.dataset import gp_history_candidates

    candidates = gp_history_candidates()
    if candidates:
        return candidates[0]
    return GP_HISTORY_PATH


def load_gp_history(path=None):
    global _CACHE
    path = resolve_gp_history_path(path)
    if _CACHE is not None and path == resolve_gp_history_path():
        return _CACHE
    if not path.exists():
        raise FileNotFoundError("Нет архива GP: {0}".format(path))
    raw = json.loads(path.read_text("utf-8"))
    records = []
    for row in raw:
        creation = parse_space_track_time(row.get("CREATION_DATE"))
        epoch = parse_space_track_time(row.get("EPOCH"))
        line1 = (row.get("TLE_LINE1") or "").strip()
        line2 = (row.get("TLE_LINE2") or "").strip()
        if not creation or not epoch or not line1 or not line2:
            continue
        records.append(
            {
                "creation": creation,
                "epoch": epoch,
                "line1": line1,
                "line2": line2,
                "gp_id": row.get("GP_ID"),
                "name": row.get("OBJECT_NAME") or "ISS (ZARYA)",
                "originator": row.get("ORIGINATOR"),
            }
        )
    records.sort(key=lambda item: item["creation"])
    if path == resolve_gp_history_path():
        _CACHE = records
    return records


def select_gp(target, cutoff=None, path=None):
    """Pick ISS elements for target time.

    Time-honest: only sets with CREATION_DATE ≤ cutoff.
    If none exist, fall back to nearest epoch and mark reconstruction.
    """
    records = load_gp_history(path)
    cutoff = as_utc(cutoff) if cutoff else None
    target = as_utc(target)
    honest = [row for row in records if cutoff is None or row["creation"] <= cutoff]
    reconstruction = False
    pool = honest
    if not pool:
        pool = records
        reconstruction = True
    if not pool:
        return None

    def sort_key(row):
        epoch = row["epoch"]
        after = 1 if epoch > target else 0
        return (after, abs((epoch - target).total_seconds()), -row["creation"].timestamp())

    chosen = min(pool, key=sort_key)
    chosen = dict(chosen)
    chosen["reconstruction"] = reconstruction
    chosen["sat"] = load_satrec(chosen["line1"], chosen["line2"])
    return chosen


def gp_source_record(chosen, path=None):
    path = resolve_gp_history_path(path)
    if chosen is None:
        return SourceRecord(
            "iss_gp_history",
            "Space-Track GP_HISTORY ISS 25544",
            str(path),
            "catalog",
            ok=False,
            error="В архиве нет подходящего набора элементов",
            units="TLE / SGP4, TEME",
        )
    notes = "GP_ID {0}; epoch {1}; CREATION_DATE {2}".format(
        chosen.get("gp_id"), iso(chosen["epoch"]), iso(chosen["creation"])
    )
    if chosen.get("reconstruction"):
        notes += "; геометрия как реконструкция: нет набора с CREATION_DATE ≤ отсечения"
    return SourceRecord(
        "iss_gp_history",
        "Space-Track GP_HISTORY ISS 25544",
        str(path),
        "catalog",
        ok=True,
        published_at=chosen["creation"],
        fetched_at=datetime.now(timezone.utc),
        payload={"epoch": iso(chosen["epoch"]), "creation": iso(chosen["creation"]), "gp_id": chosen.get("gp_id")},
        notes=notes,
        units="TLE / SGP4, TEME; CREATION_DATE ≠ EPOCH",
    )
