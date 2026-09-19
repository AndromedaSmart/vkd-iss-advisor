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
from app.demos import DEMOS, demo_form
from app.evaluate import evaluate
from app.stand import publicize_pack, stand_links
from app.timeutil import iso, utcnow


def render_page(env, form, dest, demo=""):
    html = env.get_template("index.html").render(
        request=None,
        pack=None,
        error=None,
        form=form,
        demo=demo,
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
    for name in DEMOS:
        write_fallback(name, demo_form(name))

    docs = ROOT / "docs"
    if docs.exists():
        shutil.rmtree(docs)
    (docs / "static").mkdir(parents=True)
    (docs / ".nojekyll").write_text("", encoding="utf-8")
    shutil.copy2(ROOT / "app" / "static" / "style.css", docs / "static" / "style.css")
    shutil.copy2(ROOT / "app" / "static" / "stand.js", docs / "static" / "stand.js")
    shutil.copy2(ROOT / "app" / "static" / "logo.svg", docs / "static" / "logo.svg")
    for fallback in (ROOT / "app" / "static").glob("fallback-*.json"):
        shutil.copy2(fallback, docs / "static" / fallback.name)

    env = Environment(loader=FileSystemLoader(str(ROOT / "app" / "templates")), autoescape=True)
    env.filters["iso"] = lambda value: value if isinstance(value, str) else iso(value)

    pages = [("index.html", "storm", demo_form("storm"))]
    for name in DEMOS:
        pages.append(("demo-{0}.html".format(name.replace("_", "-")), name, demo_form(name)))
    for dest_name, demo, form in pages:
        render_page(env, form, docs / dest_name, demo=demo)
        print("wrote", dest_name)


if __name__ == "__main__":
    main()
