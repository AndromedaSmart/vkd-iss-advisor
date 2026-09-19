from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.dataset import data_root, parse_geomag_forecast, ap_for_day, storm_prob_for_day
from app.evaluate import evaluate


GEOMAG = Path(__file__).resolve().parent.parent / "data" / "archives" / "ncei" / "geomag" / "20240510geomag_forecast.txt"


def test_local_bundle_is_visible():
    root = data_root()
    assert root is not None
    assert (root / "archives" / "ncei" / "three_day").exists()


def test_geomag_may10_ap():
    parsed = parse_geomag_forecast(GEOMAG.read_text("utf-8"))
    day10 = datetime(2024, 5, 10, tzinfo=timezone.utc)
    day11 = datetime(2024, 5, 11, tzinfo=timezone.utc)
    ap10, kind = ap_for_day(parsed, day10)
    assert ap10 == 97
    assert kind == "estimated"
    ap11, kind11 = ap_for_day(parsed, day11)
    assert ap11 == 106
    assert kind11 == "predicted"
    assert storm_prob_for_day(parsed, day11, "strong") == 65


def test_storm_compare_adapts_columns():
    pack = evaluate(
        {
            "mode": "historical",
            "start_utc": "2024-05-10 00:00",
            "interval_days": 4,
            "duration_hours": 6,
            "search_hours": 12,
        }
    )
    ids = [col["id"] for col in pack["ui"]["columns"]]
    assert "coverage" in ids
    assert "radio" in ids
    assert "cme" in ids
    assert "ap" in ids
    assert "storm" in ids
    assert "donki" not in ids
    assert "conj" not in ids
    assert pack["dataset"]["root"]
    may10 = pack["windows"][0]
    assert may10["coverage"]["tag"] == "ncei"
    assert may10["ap"] is not None
    assert may10["cme"]["count"] >= 1


def test_gap_days_use_donki_not_all_clear():
    pack = evaluate(
        {
            "mode": "historical",
            "start_utc": "2024-06-01 00:00",
            "interval_days": 3,
            "duration_hours": 6,
            "search_hours": 12,
        }
    )
    ids = [col["id"] for col in pack["ui"]["columns"]]
    assert "donki" in ids
    first = pack["windows"][0]
    assert first["coverage"]["tag"] in ("donki", "gap")
    assert first["donki"]["count"] >= 1
    assert "дыра" in " ".join(pack["notes"]).lower() or first["coverage"]["tag"] == "donki"


def test_full_coverage_demos_have_no_sep_holes():
    from app.demos import demo_form

    for name in ("full_may", "full_june"):
        pack = evaluate(demo_form(name))
        assert pack["windows"]
        holes = [w["day_label"] for w in pack["windows"] if w["critical_missing"] or w["completeness"] < 1]
        assert holes == [], name + " holes: " + ", ".join(holes)
        assert all((w.get("coverage") or {}).get("tag") == "ncei" for w in pack["windows"])
