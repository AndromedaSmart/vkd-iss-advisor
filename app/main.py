from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import ALGORITHM_VERSION
from app.dataset import dataset_status
from app.demos import DEFAULT_DEMO, DEMOS, demo_form
from app.evaluate import RequestError, evaluate
from app.exportfmt import pack_to_csv
from app.stand import is_public_stand, publicize_pack, stand_links
from app.timeutil import iso, utcnow

ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT.parent / "data" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="VKD ISS Advisor", version=ALGORITHM_VERSION)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))
templates.env.filters["iso"] = lambda value: value if isinstance(value, str) else iso(value)


def _save(pack):
    path = RESULTS_DIR / (pack["id"] + ".json")
    path.write_text(json.dumps(pack, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def _context(request, form, pack=None, error=None, demo=""):
    if pack and is_public_stand():
        pack = publicize_pack(pack)
    return {
        "request": request,
        "pack": pack,
        "error": error,
        "form": form,
        "demo": demo,
        "algorithm": ALGORITHM_VERSION,
        "now": iso(utcnow()),
        "stand": stand_links(static=False),
    }


def _run_form(form):
    pack = evaluate(form)
    _save(pack)
    return pack, None


def _form_from_params(
    mode="current",
    start_utc="",
    duration_hours=6.0,
    search_hours=12.0,
    interval_days=4,
    cutoff_utc="",
    refresh=False,
    freeze=False,
    offline="",
):
    return {
        "mode": mode,
        "start_utc": start_utc,
        "duration_hours": duration_hours,
        "search_hours": search_hours,
        "interval_days": interval_days,
        "cutoff_utc": cutoff_utc,
        "refresh": "on" if refresh else "",
        "freeze": "on" if freeze else "",
        "offline": offline,
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    demo = request.query_params.get("demo") or DEFAULT_DEMO
    if demo not in DEMOS:
        demo = DEFAULT_DEMO
    return templates.TemplateResponse("index.html", _context(request, demo_form(demo), pack=None, demo=demo))


@app.post("/evaluate", response_class=HTMLResponse)
def evaluate_post(
    request: Request,
    mode: str = Form("current"),
    start_utc: str = Form(""),
    duration_hours: float = Form(6.0),
    search_hours: float = Form(12.0),
    interval_days: int = Form(4),
    cutoff_utc: str = Form(""),
    refresh: str = Form(""),
    freeze: str = Form(""),
    previous_duration_hours: str = Form(""),
):
    form = {
        "mode": mode,
        "start_utc": start_utc,
        "duration_hours": duration_hours,
        "search_hours": search_hours,
        "interval_days": interval_days,
        "cutoff_utc": cutoff_utc,
        "refresh": refresh,
        "freeze": freeze,
        "previous_duration_hours": previous_duration_hours,
    }
    try:
        pack, error = _run_form(form)
    except RequestError as exc:
        pack = None
        error = str(exc)
    except Exception as exc:
        pack = None
        error = "Расчёт не выполнен: {0}".format(exc)
    return templates.TemplateResponse("index.html", _context(request, form, pack, error))


@app.get("/demo/{name}", response_class=HTMLResponse)
def demo_named(request: Request, name: str):
    if name not in DEMOS:
        name = DEFAULT_DEMO
    return templates.TemplateResponse("index.html", _context(request, demo_form(name), pack=None, demo=name))


@app.get("/api/evaluate")
def api_evaluate(
    mode: str = Query("current"),
    start_utc: str = Query(""),
    duration_hours: float = Query(6.0),
    search_hours: float = Query(12.0),
    interval_days: int = Query(4),
    cutoff_utc: str = Query(""),
    refresh: bool = Query(False),
    freeze: bool = Query(False),
    offline: str = Query(""),
):
    form = _form_from_params(
        mode, start_utc, duration_hours, search_hours, interval_days, cutoff_utc, refresh, freeze, offline
    )
    try:
        pack = evaluate(form)
        _save(pack)
        return JSONResponse(pack)
    except RequestError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


def _load_saved_pack(result_id):
    path = RESULTS_DIR / (result_id + ".json")
    if not path.exists():
        return None
    return json.loads(path.read_text("utf-8"))


def _download(body, filename, media_type):
    return Response(
        content=body.encode("utf-8"),
        media_type=media_type,
        headers={"Content-Disposition": 'attachment; filename="{0}"'.format(filename)},
    )


@app.get("/export/{result_id}.json")
def export_json(result_id: str):
    pack = _load_saved_pack(result_id)
    if pack is None:
        return JSONResponse({"error": "Расчёт не найден"}, status_code=404)
    return _download(
        json.dumps(pack, ensure_ascii=False, indent=2),
        result_id + ".json",
        "application/json; charset=utf-8",
    )


@app.get("/export/{result_id}.csv")
def export_csv(result_id: str):
    pack = _load_saved_pack(result_id)
    if pack is None:
        return JSONResponse({"error": "Расчёт не найден"}, status_code=404)
    return _download(pack_to_csv(pack), result_id + ".csv", "text/csv; charset=utf-8")


@app.get("/health")
def health():
    from app.planner_api import planner_base

    return {
        "ok": True,
        "algorithm": ALGORITHM_VERSION,
        "time": iso(utcnow()),
        "dataset": dataset_status(),
        "planner_api": planner_base(),
    }
