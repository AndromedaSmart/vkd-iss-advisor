from __future__ import annotations

import json
import os

from app import ALGORITHM_VERSION
from app.dataset import data_root
from app.demos import DEMOS, demos_in_group, js_demo_fields
from app.timeutil import MAX_INTERVAL_DAYS

DEFAULT_PLANNER_API = "http://46.29.164.87:8000"
PUBLIC_ARCHIVE_LABEL = "встроенный архив май–июнь 2024"


def planner_api_base():
    return os.environ.get("VKD_PLANNER_API") or DEFAULT_PLANNER_API


def stand_links(static=False):
    version = ALGORITHM_VERSION
    api_base = planner_api_base()
    if static:
        asset_root = "static/"
        demo_href = lambda key: "index.html?demo=" + key
        export_prefix = "export/"
        home = "index.html"
    else:
        asset_root = "/static/"
        demo_href = lambda key: "/?demo=" + key
        export_prefix = "/export/"
        home = "/"
    links = {
        "static": static,
        "asset": asset_root + "style.css?v=" + version,
        "script": asset_root + "stand.js?v=" + version,
        "home": home,
        "export_prefix": export_prefix,
        "form_action": "",
        "api_base": api_base,
        "live_api": True,
        "max_interval_days": MAX_INTERVAL_DAYS,
        "demo_fields_json": json.dumps(js_demo_fields(), ensure_ascii=False),
    }
    for key in DEMOS:
        links[key] = demo_href(key)
    links["scenario_demos"] = [
        {"key": key, "href": links[key], "label": item["label"]}
        for key, item in demos_in_group("scenario")
    ]
    links["full_demos"] = [
        {"key": key, "href": links[key], "label": item["label"]}
        for key, item in demos_in_group("full")
    ]
    return links


def publicize_pack(pack):
    """Hide machine paths on a public demo stand."""
    pack = dict(pack)
    label = PUBLIC_ARCHIVE_LABEL
    root = data_root()
    root_text = str(root) if root else ""
    if pack.get("dataset"):
        pack["dataset"] = dict(pack["dataset"])
        pack["dataset"]["root"] = label
        pack["dataset"]["three_day_dirs"] = ["data/archives/ncei/three_day", "data/archives/ncei/geomag"]
    notes = []
    for note in pack.get("notes") or []:
        if root_text:
            note = note.replace(root_text, label)
        note = note.replace("/Users/andreysorokin/Downloads/data", label)
        notes.append(note)
    pack["notes"] = notes
    sources = []
    for src in pack.get("sources") or []:
        item = dict(src)
        url = item.get("url") or ""
        if "Downloads/data" in url or "/Users/" in url or (url.startswith("/") and not url.startswith("//")):
            if not url.startswith("http"):
                item["url"] = "#"
        for key in ("notes", "error", "name"):
            text = item.get(key)
            if text and root_text:
                item[key] = text.replace(root_text, label).replace("/Users/andreysorokin/Downloads/data", label)
                item[key] = item[key].replace("/Users/andreysorokin/Projects/vkd-iss-advisor/", "")
        sources.append(item)
    pack["sources"] = sources
    return pack


def is_public_stand():
    return os.environ.get("PUBLIC_STAND") in ("1", "true", "yes")
