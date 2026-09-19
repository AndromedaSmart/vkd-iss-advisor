from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jinja2 import Environment, FileSystemLoader

from app import ALGORITHM_VERSION
from app.evaluate import evaluate
from app.main import _demo_form
from app.stand import publicize_pack, stand_links
from app.timeutil import iso, utcnow

DEMOS = (
    ("storm", _demo_form("2024-05-10 08:00", 4)),
    ("quiet", _demo_form("2024-06-18 08:00", 5)),
    ("gap", _demo_form("2024-06-01 08:00", 7)),
)


def render_page(env, form, dest):
    html = env.get_template("index.html").render(
        request=None,
        pack=None,
        error=None,
        form=form,
        algorithm=ALGORITHM_VERSION,
        now=iso(utcnow()),
        stand=stand_links(static=True),
    )
    dest.write_text(html, encoding="utf-8")


def _slim_window(window):
    out = dict(window)
    track = out.get("track")
    if track:
        track = dict(track)
        track.pop("points", None)
        out["track"] = track
    return out


def write_fallback(name, form):
    pack = publicize_pack(evaluate(dict(form, offline="on")))
    payload = {
        "windows": [_slim_window(window) for window in pack.get("windows") or []],
        "notes": pack.get("notes") or [],
        "comparison": pack.get("comparison") or {},
    }
    dest = ROOT / "app" / "static" / ("fallback-{0}.json".format(name))
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", dest.relative_to(ROOT), "windows", len(payload["windows"]))


def main():
    os.environ["VKD_LOCAL_ARCHIVES"] = "1"
    for name, form in DEMOS:
        write_fallback(name, form)

    docs = ROOT / "docs"
    if docs.exists():
        shutil.rmtree(docs)
    (docs / "static").mkdir(parents=True)
    (docs / ".nojekyll").write_text("", encoding="utf-8")
    shutil.copy2(ROOT / "app" / "static" / "style.css", docs / "static" / "style.css")
    shutil.copy2(ROOT / "app" / "static" / "stand.js", docs / "static" / "stand.js")
    for fallback in (ROOT / "app" / "static").glob("fallback-*.json"):
        shutil.copy2(fallback, docs / "static" / fallback.name)

    env = Environment(loader=FileSystemLoader(str(ROOT / "app" / "templates")), autoescape=True)
    env.filters["iso"] = lambda value: value if isinstance(value, str) else iso(value)

    pages = [
        ("index.html", DEMOS[0][1]),
        ("demo-storm.html", DEMOS[0][1]),
        ("demo-quiet.html", DEMOS[1][1]),
        ("demo-gap.html", DEMOS[2][1]),
    ]
    for name, form in pages:
        render_page(env, form, docs / name)
        print("wrote", name)


if __name__ == "__main__":
    main()
