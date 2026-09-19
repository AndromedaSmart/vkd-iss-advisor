from __future__ import annotations

import os

from app.dataset import data_root


def stand_links(static=False):
    api_base = os.environ.get("VKD_PLANNER_API") or "http://46.29.164.87:8000"
    if static:
        return {
            "static": True,
            "asset": "static/style.css",
            "script": "static/stand.js",
            "home": "index.html",
            "storm": "index.html?demo=storm",
            "quiet": "index.html?demo=quiet",
            "gap": "index.html?demo=gap",
            "export_prefix": "export/",
            "form_action": "",
            "api_base": api_base,
            "live_api": True,
        }
    return {
        "static": False,
        "asset": "/static/style.css",
        "script": "/static/stand.js",
        "home": "/",
        "storm": "/?demo=storm",
        "quiet": "/?demo=quiet",
        "gap": "/?demo=gap",
        "export_prefix": "/export/",
        "form_action": "",
        "api_base": api_base,
        "live_api": True,
    }


def publicize_pack(pack):
    """Hide machine paths on a public demo stand."""
    label = "встроенный архив май–июнь 2024"
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
