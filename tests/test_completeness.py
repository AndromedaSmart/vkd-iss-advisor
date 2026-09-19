from app.completeness import completeness_note, plain_reason, window_completeness_note


def test_plain_reason_rewrites_swpc_proton_phrase():
    assert plain_reason("Есть прогнозы SWPC протонного потока") == (
        "Есть прогноз радиации: солнечные частицы (протоны) от NOAA SWPC."
    )
    assert "протонного потока" not in plain_reason("Нет прогнозов протонного потока в период окна")
    assert "дыра" not in plain_reason("Есть прогнозы SWPC протонного потока").lower()


def test_completeness_note_explains_hole_and_data():
    hole = completeness_note(0, True, ["Нет прогнозов протонного потока в период окна"])
    assert hole.startswith("Дыра")
    assert "не значит, что безопасно" in hole
    assert "Нет прогноза радиации" in hole

    full = completeness_note(1, False, ["Есть прогнозы SWPC протонного потока"])
    assert full.startswith("Дыры нет")
    assert "солнечные частицы" in full


def test_window_completeness_note_reads_factor_confidence():
    note = window_completeness_note(
        {
            "completeness": 1,
            "critical_missing": False,
            "sep": {"confidence": "Есть прогнозы SWPC"},
            "geomagnetic": {"confidence": "Есть прогнозы Kp"},
        }
    )
    assert "Дыры нет" in note
    assert "NOAA SWPC" in note
    assert "геомагнитной обстановки" in note


def test_plain_reason_rewrites_sep_gap():
    assert plain_reason("нет данных SEP") == "Нет данных по радиации (солнечные частицы)."
