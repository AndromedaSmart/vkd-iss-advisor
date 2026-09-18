from __future__ import annotations

import json
from datetime import datetime, timezone

from app.evaluate import evaluate
from app.gp_history import select_gp


def test_cutoff_ignores_later_creation(tmp_path):
    rows = [
        {
            "CREATION_DATE": "2024-05-10T04:00:00",
            "EPOCH": "2024-05-09T20:00:00",
            "GP_ID": "early",
            "OBJECT_NAME": "ISS (ZARYA)",
            "TLE_LINE1": "1 25544U 98067A   24130.83333333  .00015010  00000-0  26311-3 0  9996",
            "TLE_LINE2": "2 25544  51.6391 189.7014 0003539 125.8174  44.7661 15.50784137451217",
        },
        {
            "CREATION_DATE": "2024-05-11T18:00:00",
            "EPOCH": "2024-05-11T12:00:00",
            "GP_ID": "late",
            "OBJECT_NAME": "ISS (ZARYA)",
            "TLE_LINE1": "1 25544U 98067A   24132.50000000  .00015010  00000-0  26311-3 0  9990",
            "TLE_LINE2": "2 25544  51.6391 180.0000 0003539 125.8174  44.7661 15.50784137451220",
        },
    ]
    path = tmp_path / "gp.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    cutoff = datetime(2024, 5, 10, 12, 30, tzinfo=timezone.utc)
    target = datetime(2024, 5, 11, 0, 0, tzinfo=timezone.utc)
    chosen = select_gp(target, cutoff=cutoff, path=path)
    assert chosen["gp_id"] == "early"
    assert chosen["reconstruction"] is False


def test_no_published_set_is_reconstruction(tmp_path):
    rows = [
        {
            "CREATION_DATE": "2024-05-12T00:00:00",
            "EPOCH": "2024-05-11T12:00:00",
            "GP_ID": "future",
            "OBJECT_NAME": "ISS (ZARYA)",
            "TLE_LINE1": "1 25544U 98067A   24132.50000000  .00015010  00000-0  26311-3 0  9990",
            "TLE_LINE2": "2 25544  51.6391 180.0000 0003539 125.8174  44.7661 15.50784137451220",
        }
    ]
    path = tmp_path / "gp.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    cutoff = datetime(2024, 5, 10, 12, 30, tzinfo=timezone.utc)
    target = datetime(2024, 5, 11, 0, 0, tzinfo=timezone.utc)
    chosen = select_gp(target, cutoff=cutoff, path=path)
    assert chosen["reconstruction"] is True


def test_historical_storm_uses_gp_history():
    pack = evaluate(
        {
            "mode": "historical",
            "start_utc": "2024-05-11 00:00",
            "duration_hours": 6,
            "search_hours": 12,
            "cutoff_utc": "2024-05-10 12:30",
        }
    )
    assert pack["orbit"]["available"] is True
    assert pack["orbit"]["reconstruction"] is False
    assert pack["orbit"]["creation"] <= "2024-05-10T12:30:00Z"
    track = pack["windows"][0]["track"]
    assert track is not None
    assert track["n_points"] > 3
    assert "iss_gp_history" in [s["id"] for s in pack["sources"]]
