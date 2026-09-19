from app.evidence_text import plain_evidence_item, plain_kind, plain_phrase, plain_rule, plain_source


def test_screenshot_evidence_is_plain():
    item = plain_evidence_item(
        {
            "provenance": "external_forecast",
            "statement": "Протонный поток на нормальном уровне",
            "rule_description": "Протонный флюкс <10 pfu (NORMAL)",
            "source_ids": ["test_swpc"],
            "rule_id": "sep.threshold.normal",
        }
    )
    assert item["kind_label"] == "Чужой прогноз"
    assert "Радиация в норме" in item["title"]
    assert "спокойный уровень" in item["detail"]
    assert item["source_id"] == "Тестовый прогноз NOAA SWPC"
    assert item["rule"] == "Спокойный уровень радиации"
    assert "pfu" not in item["detail"]
    assert "sep.threshold" not in item["rule"]


def test_plain_helpers():
    assert plain_kind("EXTERNAL_FORECAST") == "Чужой прогноз"
    assert plain_source("test_swpc") == "Тестовый прогноз NOAA SWPC"
    assert "солнечных частиц" in plain_phrase("Протонный поток на нормальном уровне")
    assert plain_rule("sep.threshold.normal") == "Спокойный уровень радиации"
    assert "ниже уровня бури" in plain_phrase("Прогноз Kp=3.00 (ниже G1)")
