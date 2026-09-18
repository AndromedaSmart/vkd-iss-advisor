from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import ALGORITHM_VERSION
from app.dataset import dataset_status
from app.evaluate import RequestError, evaluate
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


def _context(request, form, pack=None, error=None):
    if pack and is_public_stand():
        pack = publicize_pack(pack)
    return {
        "request": request,
        "pack": pack,
        "error": error,
        "form": form,
        "algorithm": ALGORITHM_VERSION,
        "now": iso(utcnow()),
        "stand": stand_links(static=False),
    }


def _demo_form(start_utc, interval_days, duration_hours=6, search_hours=12):
    return {
        "mode": "historical",
        "start_utc": start_utc,
        "duration_hours": duration_hours,
        "search_hours": search_hours,
        "interval_days": interval_days,
        "cutoff_utc": "",
        "refresh": "",
        "freeze": "",
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
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return demo_storm(request)


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


@app.get("/demo/storm", response_class=HTMLResponse)
def demo_storm(request: Request):
    form = _demo_form("2024-05-10 00:00", 4)
    try:
        pack, error = _run_form(form)
    except Exception as exc:
        pack = None
        error = str(exc)
    return templates.TemplateResponse("index.html", _context(request, form, pack, error))


@app.get("/demo/quiet", response_class=HTMLResponse)
def demo_quiet(request: Request):
    form = _demo_form("2024-06-18 00:00", 5)
    try:
        pack, error = _run_form(form)
    except Exception as exc:
        pack = None
        error = str(exc)
    return templates.TemplateResponse("index.html", _context(request, form, pack, error))


@app.get("/demo/gap", response_class=HTMLResponse)
def demo_gap(request: Request):
    form = _demo_form("2024-06-01 00:00", 7)
    try:
        pack, error = _run_form(form)
    except Exception as exc:
        pack = None
        error = str(exc)
    return templates.TemplateResponse("index.html", _context(request, form, pack, error))


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
):
    form = _form_from_params(mode, start_utc, duration_hours, search_hours, interval_days, cutoff_utc, refresh, freeze)
    try:
        pack = evaluate(form)
        _save(pack)
        return JSONResponse(pack)
    except RequestError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


@app.get("/export/{result_id}.json")
def export_json(result_id: str):
    path = RESULTS_DIR / (result_id + ".json")
    if not path.exists():
        return JSONResponse({"error": "Расчёт не найден"}, status_code=404)
    return JSONResponse(json.loads(path.read_text("utf-8")))


@app.get("/health")
def health():
    return {
        "ok": True,
        "algorithm": ALGORITHM_VERSION,
        "time": iso(utcnow()),
        "dataset": dataset_status(),
    }
