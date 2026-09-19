from app.planner_api import factor_block, level_from_grade, window_from_assessment


def test_grade_mapping():
    assert level_from_grade("benign") == "none"
    assert level_from_grade("elevated") == "watch"
    assert level_from_grade("adverse") == "warning"
    assert level_from_grade("insufficient_data") == "unknown"


def test_factor_block_from_planner():
    block = factor_block(
        {
            "factor_id": "radiation_sep",
            "grade": "benign",
            "coverage": 1,
            "confidence": "high",
            "confidence_reason": "Есть прогнозы SWPC",
            "adverse_minutes": 0,
            "evidence": [
                {
                    "statement": "Протонный поток на нормальном уровне",
                    "provenance": "external_forecast",
                    "source_ids": ["test_swpc"],
                    "rule_id": "sep.threshold.normal",
                }
            ],
            "limitations": [],
        },
        "radiation_sep",
    )
    assert block["level"] == "none"
    assert block["incomplete"] is False
    assert block["evidence"][0]["source_id"] == "test_swpc"


def test_window_from_assessment_shape():
    raw = {
        "window_start": "2024-05-10T08:00:00Z",
        "window_end": "2024-05-10T14:00:00Z",
        "duration_hours": 6,
        "factors": [
            {
                "factor_id": "radiation_sep",
                "grade": "benign",
                "coverage": 1,
                "confidence_reason": "ok",
                "adverse_minutes": 0,
                "evidence": [],
                "limitations": [],
            },
            {
                "factor_id": "geomagnetic_activity",
                "grade": "elevated",
                "coverage": 1,
                "confidence_reason": "ok",
                "adverse_minutes": 30,
                "evidence": [],
                "limitations": [],
            },
            {
                "factor_id": "mmod_meteoroid",
                "grade": "insufficient_data",
                "coverage": 0,
                "confidence_reason": "нет",
                "adverse_minutes": 0,
                "evidence": [],
                "limitations": [],
            },
        ],
        "orbit_source": {"provider": "celestrak_gp"},
        "trajectory_summary": {},
    }
    window = window_from_assessment(raw, 0, 6, True)
    assert window["id"] == "W1"
    assert window["sep"]["level"] == "none"
    assert window["geomagnetic"]["level"] == "watch"
    assert window["conjunction"]["incomplete"] is True
    assert window["coverage"]["tag"] == "ncei"


def test_assess_window_sends_v02_fields(monkeypatch):
    captured = {}

    class FakeResp(object):
        status_code = 200

        def json(self):
            return {
                "window_start": "2024-05-10T08:00:00Z",
                "window_end": "2024-05-10T14:00:00Z",
                "duration_hours": 6,
                "factors": [],
                "orbit_source": {},
                "trajectory_summary": {},
            }

    class FakeClient(object):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return FakeResp()

    monkeypatch.setattr("app.planner_api._client", lambda: FakeClient())
    from datetime import datetime, timezone
    from app.planner_api import assess_window

    start = datetime(2024, 5, 10, 8, tzinfo=timezone.utc)
    assess_window(start, 6, as_of=datetime(2024, 5, 10, 6, tzinfo=timezone.utc), mode="ignored")
    assert captured["url"].endswith("/api/assess-window")
    assert set(captured["json"].keys()) == {"window_start", "duration_hours", "as_of"}
    assert "mode" not in captured["json"]
