from app.presentation import KIND_LABELS, copy


def test_phrasebook_is_the_label_source():
    bundle = copy.client_bundle()
    assert bundle["kinds"]["external_forecast"] == "Чужой прогноз"
    assert bundle["sources"]["test_swpc"]
    assert bundle["levels"]["warning"] == "опасно"
    assert copy.kind("EXTERNAL_FORECAST") == KIND_LABELS["external_forecast"]
    assert "солнечных частиц" in copy.phrase("Протонный поток на нормальном уровне")


def test_request_and_evaluate_still_import():
    from app.evaluate import RequestError, parse_request
    from app.requestform import parse_request as parse_form

    assert parse_request is parse_form
    assert issubclass(RequestError, ValueError)
