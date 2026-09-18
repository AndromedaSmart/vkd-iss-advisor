from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.timeutil import MONTHS, as_utc, iso, parse_issued_swpc, utcnow

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"
ARCHIVE_DIR = ROOT / "data" / "archive" / "ncei"
USER_AGENT = "vkd-iss-advisor/0.1 (CosmoHackathon research prototype)"
TIMEOUT = 25.0

SWPC_PROTONS = "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json"
SWPC_KP = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
SWPC_SCALES = "https://services.swpc.noaa.gov/products/noaa-scales.json"
SWPC_FORECAST = "https://services.swpc.noaa.gov/text/3-day-forecast.txt"
CELESTRAK_TLE = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE"
CELESTRAK_GP = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=JSON"
SOCRATES_URL = (
    "https://celestrak.org/SOCRATES/table-socrates.php?CATNR=25544,&ORDER=TCA&MAX=40"
)
NCEI_FORECAST = (
    "https://www.ngdc.noaa.gov/stp/space-weather/swpc-products/"
    "daily_reports/3day_forecast/{year}/{month:02d}/"
    "{stamp}three_day_forecast.txt"
)


class SourceRecord(object):
    def __init__(
        self,
        source_id,
        name,
        url,
        role,
        ok=False,
        frozen=False,
        error=None,
        fetched_at=None,
        published_at=None,
        payload=None,
        notes=None,
        units=None,
    ):
        self.source_id = source_id
        self.name = name
        self.url = url
        self.role = role
        self.ok = ok
        self.frozen = frozen
        self.error = error
        self.fetched_at = fetched_at
        self.published_at = published_at
        self.payload = payload
        self.notes = notes or ""
        self.units = units or ""

    def as_dict(self):
        return {
            "id": self.source_id,
            "name": self.name,
            "url": self.url,
            "role": self.role,
            "ok": self.ok,
            "frozen": self.frozen,
            "error": self.error,
            "fetched_at": iso(self.fetched_at),
            "published_at": iso(self.published_at),
            "notes": self.notes,
            "units": self.units,
            "stale_minutes": _age_minutes(self.fetched_at),
        }


def _age_minutes(fetched_at):
    if fetched_at is None:
        return None
    return int((utcnow() - as_utc(fetched_at)).total_seconds() / 60)


def _cache_paths(url):
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / (digest + ".meta.json"), CACHE_DIR / (digest + ".body")


def _read_cache(url):
    meta_path, body_path = _cache_paths(url)
    if not meta_path.exists() or not body_path.exists():
        return None
    meta = json.loads(meta_path.read_text("utf-8"))
    body = body_path.read_bytes()
    fetched = datetime.fromisoformat(meta["fetched_at"])
    return meta, body, fetched


def _write_cache(url, status_code, content_type, body):
    meta_path, body_path = _cache_paths(url)
    body_path.write_bytes(body)
    meta_path.write_text(
        json.dumps(
            {
                "url": url,
                "status_code": status_code,
                "content_type": content_type,
                "fetched_at": utcnow().isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def fetch_bytes(url, frozen=False, refresh=False):
    cached = _read_cache(url)
    if frozen:
        if cached is None:
            raise RuntimeError("Источник заморожен, а локального кеша нет")
        return cached[1], cached[2], True
    if cached is not None and not refresh:
        age = utcnow() - cached[2]
        if age < timedelta(minutes=15):
            return cached[1], cached[2], True
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            response = client.get(url)
            response.raise_for_status()
            body = response.content
            _write_cache(url, response.status_code, response.headers.get("content-type", ""), body)
            return body, utcnow(), False
    except Exception as exc:
        if cached is not None:
            return cached[1], cached[2], True
        raise RuntimeError("Не удалось получить {0}: {1}".format(url, exc))


def fetch_text(url, frozen=False, refresh=False):
    body, fetched_at, from_cache = fetch_bytes(url, frozen=frozen, refresh=refresh)
    return body.decode("utf-8", errors="replace"), fetched_at, from_cache


def fetch_json(url, frozen=False, refresh=False):
    text, fetched_at, from_cache = fetch_text(url, frozen=frozen, refresh=refresh)
    return json.loads(text), fetched_at, from_cache


def ncei_forecast_url(issued):
    stamp = issued.strftime("%Y%m%d%H%M")
    return NCEI_FORECAST.format(year=issued.year, month=issued.month, stamp=stamp)


def local_ncei_forecast(issued):
    stamp = issued.strftime("%Y%m%d%H%M")
    name = stamp + "three_day_forecast.txt"
    from app.dataset import three_day_dirs

    for folder in three_day_dirs():
        path = folder / name
        if path.exists() and path.stat().st_size > 200:
            return path.read_text("utf-8"), path
    return None, ARCHIVE_DIR / name


def iter_forecast_slots(cutoff, back_days=4):
    cutoff = as_utc(cutoff)
    slots = []
    day = datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=timezone.utc)
    start = day - timedelta(days=back_days)
    cursor = start
    while cursor <= day + timedelta(days=1):
        for hour, minute in ((0, 30), (12, 30)):
            issued = cursor.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if issued <= cutoff:
                slots.append(issued)
        cursor += timedelta(days=1)
    slots.sort(reverse=True)
    return slots


def load_three_day_forecast(cutoff, frozen=False, refresh=False, current=False):
    record = SourceRecord(
        "swpc_3day",
        "NOAA SWPC 3-Day Forecast",
        SWPC_FORECAST if current else "NCEI SWPC archive",
        "external_forecast",
        units="шкалы S/G/R, Kp",
    )
    try:
        if current:
            text, fetched_at, from_cache = fetch_text(SWPC_FORECAST, frozen=frozen, refresh=refresh)
            record.url = SWPC_FORECAST
            record.fetched_at = fetched_at
            record.frozen = frozen or from_cache
            record.published_at = parse_issued_swpc(text)
            parsed = parse_three_day_forecast(text)
            parsed["text"] = text
            record.payload = parsed
            record.ok = True
            if record.published_at and record.published_at > cutoff:
                record.ok = False
                record.error = "Выпуск {0} позже отсечения {1}".format(
                    iso(record.published_at), iso(cutoff)
                )
            record.notes = "issued={0}".format(iso(record.published_at))
            return record
        last_error = None
        for issued in iter_forecast_slots(cutoff):
            local_text, local_path = local_ncei_forecast(issued)
            url = ncei_forecast_url(issued)
            try:
                if local_text is not None:
                    text = local_text
                    fetched_at = datetime.fromtimestamp(local_path.stat().st_mtime, timezone.utc)
                    record.notes = "локальная копия архива " + local_path.name
                    record.url = str(local_path)
                else:
                    from app.dataset import data_root

                    if data_root() is not None:
                        last_error = "нет локального 3-day для {0}".format(issued.strftime("%Y%m%d%H%M"))
                        continue
                    text, fetched_at, from_cache = fetch_text(url, frozen=frozen, refresh=refresh)
                    record.notes = "кеш" if from_cache else "NCEI"
                    record.url = url
                published = parse_issued_swpc(text) or issued
                if published > cutoff:
                    continue
                parsed = parse_three_day_forecast(text)
                parsed["text"] = text
                record.payload = parsed
                record.fetched_at = fetched_at
                record.published_at = published
                record.ok = True
                record.frozen = frozen
                record.notes += "; issued={0}".format(iso(published))
                return record
            except Exception as exc:
                last_error = str(exc)
                continue
        record.error = last_error or "Нет выпуска 3-day forecast с issued ≤ отсечения"
        return record
    except Exception as exc:
        record.error = str(exc)
        return record


def parse_three_day_forecast(text):
    issued = parse_issued_swpc(text)
    s_probs = _parse_s1_probs(text, issued)
    kp_bins = _parse_kp_table(text, issued)
    r12_probs = _parse_radio_probs(text, issued, "R1-R2")
    r3_probs = _parse_radio_probs(text, issued, "R3 or greater")
    observed_s = "above S-scale" in text or "above S-scale storm" in text
    if "below S-scale" in text:
        observed_s = False
    observed_kp = _parse_observed_kp(text)
    observed_r = "Radio blackouts reaching the R" in text
    return {
        "issued": issued,
        "s1_probs": s_probs,
        "kp_bins": kp_bins,
        "r12_probs": r12_probs,
        "r3_probs": r3_probs,
        "observed_s_storm": observed_s,
        "observed_kp": observed_kp,
        "observed_r_storm": observed_r,
        "rationale_s": _section_rationale(text, "B. NOAA Solar Radiation"),
        "rationale_g": _section_rationale(text, "A. NOAA Geomagnetic"),
        "rationale_r": _section_rationale(text, "C. NOAA Radio"),
        "product_excerpt": "\n".join(text.splitlines()[:8]),
    }


def _parse_s1_probs(text, issued):
    lines = text.splitlines()
    probs = []
    for i, line in enumerate(lines):
        if "S1 or greater" not in line:
            continue
        header = lines[i - 1] if i else ""
        dates = _dates_from_header(header, issued)
        raw = re.findall(r"(\d+)\s*%", line)
        for idx, pct in enumerate(raw):
            day = dates[idx] if idx < len(dates) else None
            if day is None:
                continue
            start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            probs.append(
                {
                    "start": start,
                    "end": start + timedelta(days=1),
                    "s1_percent": int(pct),
                }
            )
        break
    return probs


def _parse_radio_probs(text, issued, marker):
    lines = text.splitlines()
    probs = []
    for i, line in enumerate(lines):
        if marker not in line:
            continue
        header = lines[i - 1] if i else ""
        dates = _dates_from_header(header, issued)
        raw = re.findall(r"(\d+)\s*%", line)
        key = "r3_percent" if "R3" in marker else "r12_percent"
        for idx, pct in enumerate(raw):
            day = dates[idx] if idx < len(dates) else None
            if day is None:
                continue
            start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            probs.append(
                {
                    "start": start,
                    "end": start + timedelta(days=1),
                    key: int(pct),
                }
            )
        break
    return probs


def _dates_from_header(header, issued):
    found = re.findall(r"([A-Z][a-z]{2})\s+(\d{1,2})", header)
    year = issued.year if issued else utcnow().year
    dates = []
    last_month = None
    for mon, day in found:
        month = MONTHS.get(mon)
        if month is None:
            continue
        if last_month is not None and month < last_month:
            year += 1
        last_month = month
        dates.append(datetime(year, month, int(day), tzinfo=timezone.utc))
    return dates


def _parse_kp_table(text, issued):
    bins = []
    lines = text.splitlines()
    header_idx = None
    header_dates = []
    for i, line in enumerate(lines):
        if re.search(r"NOAA Kp index breakdown", line):
            for j in range(i + 1, min(i + 6, len(lines))):
                dates = _dates_from_header(lines[j], issued)
                if len(dates) >= 2:
                    header_idx = j
                    header_dates = dates
                    break
            break
    if header_idx is None:
        return bins
    row_re = re.compile(
        r"(\d{2})-(\d{2})UT\s+(.+)$"
    )
    value_re = re.compile(r"([0-9]+\.[0-9]+|[0-9]+)(?:\s*\(G(\d)\))?")
    for line in lines[header_idx + 1 : header_idx + 12]:
        match = row_re.search(line)
        if not match:
            if line.strip().startswith("Rationale"):
                break
            continue
        h0 = int(match.group(1))
        h1 = int(match.group(2))
        if h1 == 0:
            h1 = 24
        values = value_re.findall(match.group(3))
        for idx, (kp_s, g_s) in enumerate(values[: len(header_dates)]):
            day = header_dates[idx]
            start = day.replace(hour=h0, minute=0, second=0, microsecond=0)
            end = day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=h1)
            if h1 == 24:
                end = day + timedelta(days=1)
            kp = float(kp_s)
            g = int(g_s) if g_s else kp_to_g(kp)
            bins.append({"start": start, "end": end, "kp": kp, "g": g})
    return bins


def kp_to_g(kp):
    if kp >= 9:
        return 5
    if kp >= 8:
        return 4
    if kp >= 7:
        return 3
    if kp >= 6:
        return 2
    if kp >= 5:
        return 1
    return 0


def _parse_observed_kp(text):
    match = re.search(r"greatest observed 3 hr Kp over the past 24 hours was ([0-9.]+)", text)
    if not match:
        return None
    return float(match.group(1))


def _section_rationale(text, heading_prefix):
    lines = text.splitlines()
    capture = False
    buf = []
    for line in lines:
        if line.startswith(heading_prefix):
            capture = True
            continue
        if capture and line.startswith("Rationale:"):
            buf.append(line[len("Rationale:") :].strip())
            continue
        if capture and buf:
            if line.startswith("C. ") or line.startswith("B. ") or line.startswith("A. "):
                break
            if line.strip() == "":
                if len(buf) > 1:
                    break
                continue
            buf.append(line.strip())
    return " ".join(buf).strip()


def load_goes_protons(frozen=False, refresh=False):
    record = SourceRecord(
        "goes_protons",
        "NOAA SWPC GOES integral protons",
        SWPC_PROTONS,
        "observation",
        units="p/(cm² s sr), канал ≥10 MeV",
    )
    try:
        data, fetched_at, from_cache = fetch_json(SWPC_PROTONS, frozen=frozen, refresh=refresh)
        series = []
        for row in data:
            if row.get("energy") != ">=10 MeV":
                continue
            t = datetime.fromisoformat(row["time_tag"].replace("Z", "+00:00"))
            series.append({"time": as_utc(t), "flux": float(row["flux"]), "satellite": row.get("satellite")})
        record.payload = series
        record.fetched_at = fetched_at
        record.ok = True
        record.frozen = frozen or from_cache
        if series:
            record.published_at = series[-1]["time"]
            record.notes = "точек ≥10 MeV: {0}; спутник {1}".format(
                len(series), series[-1].get("satellite")
            )
        else:
            record.ok = False
            record.error = "В ответе нет канала ≥10 MeV"
        return record
    except Exception as exc:
        record.error = str(exc)
        return record


def load_kp_now(frozen=False, refresh=False):
    record = SourceRecord(
        "swpc_kp",
        "NOAA SWPC planetary K-index",
        SWPC_KP,
        "observation",
        units="Kp",
    )
    try:
        data, fetched_at, from_cache = fetch_json(SWPC_KP, frozen=frozen, refresh=refresh)
        series = []
        for row in data:
            t = datetime.fromisoformat(row["time_tag"].replace("Z", "+00:00"))
            series.append(
                {
                    "time": as_utc(t),
                    "kp": float(row.get("estimated_kp") or row.get("kp_index") or 0),
                }
            )
        record.payload = series
        record.fetched_at = fetched_at
        record.ok = True
        record.frozen = frozen or from_cache
        if series:
            record.published_at = series[-1]["time"]
        return record
    except Exception as exc:
        record.error = str(exc)
        return record


def load_noaa_scales(frozen=False, refresh=False):
    record = SourceRecord(
        "noaa_scales",
        "NOAA Scales",
        SWPC_SCALES,
        "observation",
        units="шкалы R/S/G",
    )
    try:
        data, fetched_at, from_cache = fetch_json(SWPC_SCALES, frozen=frozen, refresh=refresh)
        record.payload = data
        record.fetched_at = fetched_at
        record.ok = True
        record.frozen = frozen or from_cache
        current = data.get("0") or {}
        stamp = "{0} {1}".format(current.get("DateStamp"), current.get("TimeStamp"))
        try:
            record.published_at = as_utc(datetime.fromisoformat(stamp.replace(" ", "T")))
        except Exception:
            record.published_at = fetched_at
        return record
    except Exception as exc:
        record.error = str(exc)
        return record


def load_iss_tle(frozen=False, refresh=False):
    record = SourceRecord(
        "celestrak_iss",
        "CelesTrak GP ISS (25544)",
        CELESTRAK_TLE,
        "catalog",
        units="TLE / SGP4, TEME",
    )
    try:
        text, fetched_at, from_cache = fetch_text(CELESTRAK_TLE, frozen=frozen, refresh=refresh)
        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
        if len(lines) < 3:
            raise RuntimeError("Неполный TLE")
        record.payload = {"name": lines[0].strip(), "line1": lines[1], "line2": lines[2]}
        record.fetched_at = fetched_at
        record.ok = True
        record.frozen = frozen or from_cache
        record.notes = lines[0].strip()
        try:
            gp, _, _ = fetch_json(CELESTRAK_GP, frozen=frozen, refresh=refresh)
            if gp:
                record.published_at = as_utc(
                    datetime.fromisoformat(gp[0]["EPOCH"].replace("Z", "+00:00"))
                )
                record.notes += "; epoch={0}".format(gp[0]["EPOCH"])
                record.payload["epoch"] = gp[0]["EPOCH"]
                record.payload["gp"] = gp[0]
        except Exception:
            pass
        return record
    except Exception as exc:
        record.error = str(exc)
        return record


class _HTMLText(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self._parts = []
        self.text = ""

    def handle_data(self, data):
        self._parts.append(data)

    def close(self):
        HTMLParser.close(self)
        self.text = re.sub(r"\s+", " ", "".join(self._parts)).strip()
        return self.text


def _strip_html(chunk):
    parser = _HTMLText()
    try:
        parser.feed(chunk)
        parser.close()
        return parser.text
    except Exception:
        return re.sub(r"<[^>]+>", "", chunk)


def load_socrates(frozen=False, refresh=False):
    record = SourceRecord(
        "socrates",
        "CelesTrak SOCRATES Plus ISS",
        SOCRATES_URL,
        "external_forecast",
        units="TCA UTC, км, max probability",
    )
    try:
        text, fetched_at, from_cache = fetch_text(SOCRATES_URL, frozen=frozen, refresh=refresh)
        events = parse_socrates_html(text)
        record.payload = events
        record.fetched_at = fetched_at
        record.ok = True
        record.frozen = frozen or from_cache
        current = re.search(r"Data current as of ([0-9A-Za-z:\s]+UTC)", text)
        if current:
            record.notes = current.group(1).strip()
        record.notes = (record.notes + "; событий={0}".format(len(events))).strip("; ")
        return record
    except Exception as exc:
        record.error = str(exc)
        return record


def parse_socrates_html(text):
    tables = text.split("<table")
    target = ""
    for part in tables[1:]:
        chunk = "<table" + part.split("</table>")[0] + "</table>"
        if "TCA" in chunk and "Min" in chunk:
            target = chunk
            break
    if not target:
        return []
    tds = re.findall(r"<td[^>]*>(.*?)</td>", target, flags=re.I | re.S)
    cells = [_strip_html(td) for td in tds]
    events = []
    i = 0
    while i < len(cells):
        if cells[i] != "GP Data":
            i += 1
            continue
        block = cells[i : i + 13]
        if len(block) < 13:
            break
        try:
            tca = as_utc(datetime.strptime(block[4][:19], "%Y-%m-%d %H:%M:%S"))
            min_range = float(block[5])
            rel_speed = float(block[6])
            max_prob = float(block[11].replace("E", "e"))
            dilution = float(block[12])
        except Exception:
            i += 1
            continue
        norad1, name1 = block[1], block[2]
        norad2, name2 = block[8], block[9]
        if norad1 == "25544":
            other_id, other_name = norad2, name2
        else:
            other_id, other_name = norad1, name1
        events.append(
            {
                "tca": tca,
                "min_range_km": min_range,
                "relative_speed_km_s": rel_speed,
                "max_probability": max_prob,
                "dilution_km": dilution,
                "other_id": other_id,
                "other_name": other_name,
                "dse_iss": _safe_float(block[3]),
            }
        )
        i += 13
    return events


def _safe_float(value):
    try:
        return float(value)
    except Exception:
        return None
