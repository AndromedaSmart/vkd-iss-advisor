from __future__ import annotations

import json
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


def render_page(env, form, pack, dest):
    html = env.get_template("index.html").render(
        request=None,
        pack=publicize_pack(pack),
        error=None,
        form=form,
        algorithm=ALGORITHM_VERSION,
        now=iso(utcnow()),
        stand=stand_links(static=True),
    )
    dest.write_text(html, encoding="utf-8")


def main():
    docs = ROOT / "docs"
    if docs.exists():
        shutil.rmtree(docs)
    (docs / "static").mkdir(parents=True)
    (docs / "export").mkdir(parents=True)
    (docs / ".nojekyll").write_text("", encoding="utf-8")
    shutil.copy2(ROOT / "app" / "static" / "style.css", docs / "static" / "style.css")

    env = Environment(loader=FileSystemLoader(str(ROOT / "app" / "templates")), autoescape=True)
    env.filters["iso"] = lambda value: value if isinstance(value, str) else iso(value)

    scenarios = [
        ("index.html", _demo_form("2024-05-10 00:00", 4)),
        ("demo-storm.html", _demo_form("2024-05-10 00:00", 4)),
        ("demo-quiet.html", _demo_form("2024-06-18 00:00", 5)),
        ("demo-gap.html", _demo_form("2024-06-01 00:00", 7)),
    ]
    for name, form in scenarios:
        pack = evaluate(form)
        (docs / "export" / (pack["id"] + ".json")).write_text(
            json.dumps(publicize_pack(dict(pack)), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        render_page(env, form, pack, docs / name)
        print("wrote", name, pack["id"])


if __name__ == "__main__":
    main()
