from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.ingest import SourceRecord
from app.timeutil import MONTHS, as_utc, iso, parse_issued_swpc, utcnow

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOWNLOADS = Path("/Users/andreysorokin/Downloads/data")


def data_root():
    env = os.environ.get("VKD_DATA_DIR")
    if env:
        path = Path(env)
        if path.exists():
            return path
    for candidate in (
        PROJECT_ROOT / "data",
        PROJECT_ROOT / "data" / "bundle",
        DEFAULT_DOWNLOADS,
    ):
        if candidate.exists() and (candidate / "archives").exists():
            return candidate
    return None


def three_day_dirs():
    dirs = [PROJECT_ROOT / "data" / "archive" / "ncei"]
    root = data_root()
    if root:
        dirs.insert(0, root / "archives" / "ncei" / "three_day")
        dirs.insert(1, root / "archives" / "ncei" / "geomag")
    return [path for path in dirs if path.exists()]


def geomag_dir():
    root = data_root()
    if root:
        path = root / "archives" / "ncei" / "geomag"
        if path.exists():
            return path
    return None


def gp_history_candidates():
    paths = [PROJECT_ROOT / "data" / "archive" / "iss_gp_history_2024.json"]
    root = data_root()
    if root:
        paths.insert(0, root / "archives" / "spacetrack" / "iss_gp_history_2024.json")
    return [path for path in paths if path.exists()]


_NOTIF_CACHE = None
_CME_CACHE = None


def load_notifications():
    global _NOTIF_CACHE
    if _NOTIF_CACHE is not None:
        return _NOTIF_CACHE
    root = data_root()
    paths = []
    if root:
        paths.append(root / "notifications_may_june.json")
        paths.append(root / "archives" / "donki" / "notifications_may_june.json")
    records = []
    for path in paths:
        if not path.exists():
            continue
        raw = json.loads(path.read_text("utf-8"))
        for row in raw:
            issued = _parse_donki_time(row.get("messageIssueTime"))
            if issued is None:
                continue
            records.append(
                {
                    "type": row.get("messageType") or "?",
                    "id": row.get("messageID"),
                    "url": row.get("messageURL"),
                    "issued": issued,
                    "body": row.get("messageBody") or "",
                    "path": str(path),
                }
            )
        break
    _NOTIF_CACHE = records
    return records


def load_cme_catalog():
    global _CME_CACHE
    if _CME_CACHE is not None:
        return _CME_CACHE
    root = data_root()
    path = root / "cme_analysis_may_june.json" if root else None
    records = []
    if path and path.exists():
        raw = json.loads(path.read_text("utf-8"))
        for row in raw:
            start = _parse_donki_time(row.get("associatedCMEstartTime") or row.get("time21_5"))
            submitted = _parse_donki_time(row.get("submissionTime"))
            if start is None:
                continue
            lon = row.get("longitude")
            half = row.get("halfAngle") or 0
            records.append(
                {
                    "start": start,
                    "submitted": submitted,
                    "speed": row.get("speed"),
                    "longitude": lon,
                    "latitude": row.get("latitude"),
                    "half_angle": half,
                    "cme_type": row.get("type"),
                    "earthward": _earthward(lon, half),
                    "id": row.get("associatedCMEID"),
                    "link": row.get("associatedCMELink") or row.get("link"),
                    "note": row.get("note") or "",
                }
            )
    _CME_CACHE = records
    return records


def _earthward(lon, half):
    if lon is None:
        return False
    width = max(float(half or 0), 30.0)
    return abs(float(lon)) <= width + 10.0


def _parse_donki_time(text):
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        return as_utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def find_three_day_file(issued):
    stamp = issued.strftime("%Y%m%d%H%M")
    name = stamp + "three_day_forecast.txt"
    for folder in three_day_dirs():
        path = folder / name
        if path.exists() and path.stat().st_size > 200:
            return path
    return None


def day_has_three_day(day):
    for hour, minute in ((0, 30), (12, 30)):
        issued = datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)
        if find_three_day_file(issued):
            return True
    return False


def load_geomag_forecast(cutoff):
    record = SourceRecord(
        "swpc_geomag",
        "NOAA SWPC Geomag Forecast",
        "NCEI geomag archive",
        "external_forecast",
        units="Ap, вероятности бурь, Kp",
    )
    folder = geomag_dir()
    if folder is None:
        record.error = "Локальный архив geomag не найден"
        return record
    cutoff = as_utc(cutoff)
    candidates = sorted(folder.glob("*geomag_forecast.txt"), reverse=True)
    last_error = None
    for path in candidates:
        try:
            text = path.read_text("utf-8")
        except Exception as exc:
            last_error = str(exc)
            continue
        issued = parse_issued_swpc(text)
        if issued is None:
            stamp = re.match(r"(\d{8})", path.name)
            if stamp:
                issued = datetime.strptime(stamp.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)
        if issued is None or issued > cutoff:
            continue
        parsed = parse_geomag_forecast(text)
        parsed["text"] = text
        record.payload = parsed
        record.ok = True
        record.published_at = issued
        record.fetched_at = utcnow()
        record.url = str(path)
        record.notes = "локальный архив {0}; issued={1}".format(path.name, iso(issued))
        return record
    record.error = last_error or "Нет geomag forecast с issued ≤ отсечения"
    return record


def parse_geomag_forecast(text):
    issued = parse_issued_swpc(text)
    observed = _parse_ap_line(text, "Observed Ap", issued)
    estimated = _parse_ap_line(text, "Estimated Ap", issued)
    predicted = _parse_predicted_ap(text, issued)
    probs = _parse_storm_probs(text, issued)
    return {
        "issued": issued,
        "observed_ap": observed,
        "estimated_ap": estimated,
        "predicted_ap": predicted,
        "storm_probs": probs,
    }


def _parse_ap_line(text, prefix, issued=None):
    match = re.search(prefix + r"\s+(\d{1,2}\s+\w+)\s+(\d+)", text)
    if not match:
        return None
    day = _parse_day_token(match.group(1), issued)
    return {"day": day, "ap": int(match.group(2))}


def _parse_predicted_ap(text, issued=None):
    match = re.search(
        r"Predicted Ap\s+(\d{1,2}\s+\w+)-(\d{1,2}\s+\w+)\s+([0-9]{2,3})-([0-9]{2,3})-([0-9]{2,3})",
        text,
    )
    if not match:
        return []
    start = _parse_day_token(match.group(1), issued)
    values = [int(match.group(i)) for i in (3, 4, 5)]
    out = []
    if start is None:
        return out
    for idx, ap in enumerate(values):
        out.append({"day": start + timedelta(days=idx), "ap": ap})
    return out


def _parse_storm_probs(text, issued=None):
    labels = {
        "Active": "active",
        "Minor storm": "minor",
        "Moderate storm": "moderate",
        "Strong-Extreme storm": "strong",
    }
    header = re.search(r"NOAA Geomagnetic Activity Probabilities\s+(\d{1,2}\s+\w+)-(\d{1,2}\s+\w+)", text)
    start = _parse_day_token(header.group(1), issued) if header else None
    rows = {}
    for title, key in labels.items():
        match = re.search(title + r"\s+([0-9]{2})/([0-9]{2})/([0-9]{2})", text)
        if not match or start is None:
            continue
        rows[key] = []
        for idx in range(3):
            rows[key].append(
                {"day": start + timedelta(days=idx), "percent": int(match.group(idx + 1))}
            )
    return rows


def _parse_day_token(token, issued):
    parts = token.split()
    if len(parts) < 2:
        return None
    day = int(parts[0])
    month = MONTHS.get(parts[1][:3])
    year = issued.year if issued else 2024
    if month is None:
        return None
    return datetime(year, month, day, tzinfo=timezone.utc)


def ap_for_day(parsed, day):
    if not parsed:
        return None
    target = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    for item in parsed.get("predicted_ap") or []:
        if item["day"].date() == target.date():
            return item["ap"], "predicted"
    est = parsed.get("estimated_ap")
    if est and est["day"] and est["day"].date() == target.date():
        return est["ap"], "estimated"
    obs = parsed.get("observed_ap")
    if obs and obs["day"] and obs["day"].date() == target.date():
        return obs["ap"], "observed"
    return None


def storm_prob_for_day(parsed, day, key="strong"):
    rows = (parsed or {}).get("storm_probs", {}).get(key) or []
    for item in rows:
        if item["day"].date() == day.date():
            return item["percent"]
    return None


def notifications_for_window(start, end, cutoff):
    pad = timedelta(hours=12)
    hits = []
    for row in load_notifications():
        if cutoff and row["issued"] > cutoff:
            continue
        if start - pad <= row["issued"] <= end + pad or row["issued"].date() == start.date():
            hits.append(row)
    return hits


def cmes_for_window(start, end, cutoff):
    hits = []
    lookback = start - timedelta(days=2)
    for row in load_cme_catalog():
        if cutoff and row["submitted"] and row["submitted"] > cutoff:
            continue
        if lookback <= row["start"] <= end:
            hits.append(row)
    hits.sort(key=lambda item: (-(item["speed"] or 0), item["start"]))
    return hits


def coverage_for_day(day, forecast_ok, donki_hits):
    labels = []
    if forecast_ok or day_has_three_day(day):
        labels.append("3-day")
    if geomag_dir() is not None:
        name = day.strftime("%Y%m%d") + "geomag_forecast.txt"
        if (geomag_dir() / name).exists():
            labels.append("geomag")
    if donki_hits:
        labels.append("DONKI")
    if "3-day" in labels:
        tag = "ncei"
    elif "DONKI" in labels:
        tag = "donki"
    else:
        tag = "gap"
    return {"tag": tag, "labels": labels}


def dataset_status():
    root = data_root()
    return {
        "root": str(root) if root else None,
        "three_day_dirs": [str(path) for path in three_day_dirs()],
        "notifications": len(load_notifications()),
        "cmes": len(load_cme_catalog()),
        "geomag": str(geomag_dir()) if geomag_dir() else None,
    }
