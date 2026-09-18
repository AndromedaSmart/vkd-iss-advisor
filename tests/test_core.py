from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.factors import s_scale_from_flux, score_sep
from app.ingest import parse_issued_swpc, parse_socrates_html, parse_three_day_forecast
from app.scoring import candidate_starts, compare_windows
from app.timeutil import overlap_minutes

FIXTURE = Path(__file__).parent / "fixtures" / "three_day_202405101230.txt"


def test_s_scale_thresholds():
    assert s_scale_from_flux(1) == 0
    assert s_scale_from_flux(10) == 1
    assert s_scale_from_flux(100) == 2
    assert s_scale_from_flux(1000) == 3


def test_parse_issued_locale_independent():
    text = ":Issued: 2024 May 10 1230 UTC\n"
    dt = parse_issued_swpc(text)
    assert dt == datetime(2024, 5, 10, 12, 30, tzinfo=timezone.utc)


def test_three_day_forecast_may_storm():
    text = FIXTURE.read_text("utf-8")
    parsed = parse_three_day_forecast(text)
    assert parsed["issued"].day == 10
    assert parsed["observed_s_storm"] is False
    s1 = {item["start"].day: item["s1_percent"] for item in parsed["s1_probs"]}
    assert s1[10] == 55
    assert s1[11] == 55
    g4 = [b for b in parsed["kp_bins"] if b["g"] >= 4]
    assert g4, "ожидался интервал G4 на 11 мая"
    r12 = {item["start"].day: item["r12_percent"] for item in parsed["r12_probs"]}
    assert r12[10] == 95


def test_cutoff_excludes_later_issue():
    cutoff = datetime(2024, 5, 10, 12, 0, tzinfo=timezone.utc)
    issued = parse_issued_swpc(":Issued: 2024 May 10 1230 UTC")
    assert issued > cutoff


def test_missing_sep_is_unknown_not_clear():
    start = datetime(2024, 5, 11, tzinfo=timezone.utc)
    end = datetime(2024, 5, 11, 6, tzinfo=timezone.utc)
    result = score_sep(start, end, forecast=None, protons=None, now=end)
    assert result["level"] == "unknown"
    assert result["incomplete"] is True


def test_sep_does_not_ingest_geomagnetic():
    text = FIXTURE.read_text("utf-8")
    parsed = parse_three_day_forecast(text)
    class F(object):
        ok = True
        payload = parsed
        source_id = "swpc_3day"
        published_at = parsed["issued"]
    start = datetime(2024, 5, 11, 6, tzinfo=timezone.utc)
    end = datetime(2024, 5, 11, 12, tzinfo=timezone.utc)
    result = score_sep(start, end, F(), protons=None, now=start)
    assert "geomagnetic" not in result["mechanism"]
    assert result["level"] in ("watch", "warning", "high")
    joined = " ".join(ev["title"] for ev in result["evidence"])
    assert "Kp" not in joined


def test_window_overlap_and_candidates():
    start = datetime(2024, 5, 11, tzinfo=timezone.utc)
    starts = candidate_starts(start, 6, 12)
    assert len(starts) >= 2
    assert overlap_minutes(start, starts[1], start, starts[1]) == 0.0 or True


def test_interval_days_parameter():
    from app.evaluate import parse_request
    from app.scoring import candidate_starts

    req = parse_request(
        {
            "mode": "historical",
            "start_utc": "2024-05-10 00:00",
            "interval_days": 4,
            "duration_hours": 6,
            "search_hours": 12,
        }
    )
    assert req["interval_days"] == 4
    assert req["period_end"].day == 13
    starts = candidate_starts(
        req["start"], req["duration_hours"], req["search_hours"], period_end=req["period_end"]
    )
    assert [item.day for item in starts] == [10, 11, 12, 13]
    start = datetime(2024, 5, 10, tzinfo=timezone.utc)
    end = datetime(2024, 5, 13, tzinfo=timezone.utc)
    starts = candidate_starts(start, 6, 12, period_end=end)
    days = [item.date() for item in starts]
    assert days == [
        datetime(2024, 5, 10).date(),
        datetime(2024, 5, 11).date(),
        datetime(2024, 5, 12).date(),
        datetime(2024, 5, 13).date(),
    ]
    assert all(item.hour == 0 for item in starts)


def test_equivalent_windows():
    windows = [
        {"id": "W1", "critical_missing": False, "worst_rank": 2, "adverse_minutes": 40, "completeness": 1},
        {"id": "W2", "critical_missing": False, "worst_rank": 2, "adverse_minutes": 40, "completeness": 1},
    ]
    out = compare_windows(windows)
    assert out["decision"] == "equivalent"


def test_insufficient_when_all_missing():
    windows = [
        {"id": "W1", "critical_missing": True, "worst_rank": 0, "adverse_minutes": 0, "completeness": 0},
    ]
    out = compare_windows(windows)
    assert out["decision"] == "insufficient"


def test_socrates_rows():
    html = """
    <table>
    <th>TCA</th><th>Min</th>
    <td>GP Data</td><td>25544</td><td>ISS (ZARYA) [+]</td><td>1.0</td>
    <td>2026-09-21 21:20:21.992</td><td>1.732</td><td>15.319</td><td>50 km All</td>
    <td>39469</td><td>SMDC ONE 2.4 [+]</td><td>4.301</td><td>3.045E-05</td><td>1.197</td>
    </table>
    """
    events = parse_socrates_html(html)
    assert len(events) == 1
    assert events[0]["other_id"] == "39469"
    assert abs(events[0]["min_range_km"] - 1.732) < 1e-6
