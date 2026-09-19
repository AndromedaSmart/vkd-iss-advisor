from fastapi.testclient import TestClient

from app.evaluate import evaluate
from app.exportfmt import CSV_COLUMNS, pack_to_csv
from app.main import RESULTS_DIR, _save, app


def test_pack_csv_has_header_and_rows():
    pack = evaluate(
        {
            "mode": "historical",
            "start_utc": "2024-04-15 08:00",
            "interval_days": 2,
            "duration_hours": 6,
            "search_hours": 12,
            "offline": "on",
        }
    )
    text = pack_to_csv(pack)
    header = text.splitlines()[0]
    assert header == ",".join(CSV_COLUMNS)
    assert "W1" in text
    assert "2024-04-15" in text
    assert text.count("\n") >= 3


def test_export_endpoints_download_json_and_csv():
    pack = evaluate(
        {
            "mode": "historical",
            "start_utc": "2024-04-15 08:00",
            "interval_days": 2,
            "duration_hours": 6,
            "search_hours": 12,
            "offline": "on",
        }
    )
    _save(pack)
    assert (RESULTS_DIR / (pack["id"] + ".json")).exists()
    client = TestClient(app)
    json_resp = client.get("/export/{0}.json".format(pack["id"]))
    assert json_resp.status_code == 200
    assert "attachment" in json_resp.headers.get("content-disposition", "")
    assert json_resp.json()["id"] == pack["id"]
    csv_resp = client.get("/export/{0}.csv".format(pack["id"]))
    assert csv_resp.status_code == 200
    assert "attachment" in csv_resp.headers.get("content-disposition", "")
    assert csv_resp.text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert "W1" in csv_resp.text


def test_pack_csv_has_header_and_rows():
    pack = evaluate(
        {
            "mode": "historical",
            "start_utc": "2024-04-15 08:00",
            "interval_days": 2,
            "duration_hours": 6,
            "search_hours": 12,
            "offline": "on",
        }
    )
    text = pack_to_csv(pack)
    header = text.splitlines()[0]
    assert header == ",".join(CSV_COLUMNS)
    assert "W1" in text
    assert "2024-04-15" in text
    assert text.count("\n") >= 3
