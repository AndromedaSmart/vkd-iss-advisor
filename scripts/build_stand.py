from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jinja2 import Environment, FileSystemLoader

from app import ALGORITHM_VERSION
from app.main import _demo_form
from app.stand import stand_links
from app.timeutil import iso, utcnow


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


def main():
    docs = ROOT / "docs"
    if docs.exists():
        shutil.rmtree(docs)
    (docs / "static").mkdir(parents=True)
    (docs / ".nojekyll").write_text("", encoding="utf-8")
    shutil.copy2(ROOT / "app" / "static" / "style.css", docs / "static" / "style.css")
    shutil.copy2(ROOT / "app" / "static" / "stand.js", docs / "static" / "stand.js")

    env = Environment(loader=FileSystemLoader(str(ROOT / "app" / "templates")), autoescape=True)
    env.filters["iso"] = lambda value: value if isinstance(value, str) else iso(value)

    scenarios = [
        ("index.html", _demo_form("2024-05-10 08:00", 4)),
        ("demo-storm.html", _demo_form("2024-05-10 08:00", 4)),
        ("demo-quiet.html", _demo_form("2024-06-18 08:00", 5)),
        ("demo-gap.html", _demo_form("2024-06-01 08:00", 7)),
    ]
    for name, form in scenarios:
        render_page(env, form, docs / name)
        print("wrote", name)


if __name__ == "__main__":
    main()
