from __future__ import annotations

DEFAULT_DEMO = "storm"

# Scenarios keep the original story buttons. `full` is the densest NCEI coverage:
# 1–14 May and 17–30 June 2024 have completeness 1.00 and no SEP holes.
DEMOS = {
    "storm": {
        "mode": "historical",
        "start_utc": "2024-05-10 08:00",
        "duration_hours": 6,
        "interval_days": 4,
        "search_hours": 12,
        "cutoff_utc": "",
        "label": "Буря · 10–13 мая 2024",
        "group": "scenario",
    },
    "quiet": {
        "mode": "historical",
        "start_utc": "2024-06-18 08:00",
        "duration_hours": 6,
        "interval_days": 5,
        "search_hours": 12,
        "cutoff_utc": "",
        "label": "Тихо · 18–22 июня 2024",
        "group": "scenario",
    },
    "gap": {
        "mode": "historical",
        "start_utc": "2024-06-01 08:00",
        "duration_hours": 6,
        "interval_days": 7,
        "search_hours": 12,
        "cutoff_utc": "",
        "label": "Дыра · 1–7 июня 2024",
        "group": "scenario",
    },
    "full_may": {
        "mode": "historical",
        "start_utc": "2024-05-01 08:00",
        "duration_hours": 6,
        "interval_days": 14,
        "search_hours": 12,
        "cutoff_utc": "",
        "label": "1–14 мая 2024",
        "group": "full",
    },
    "full_june": {
        "mode": "historical",
        "start_utc": "2024-06-17 08:00",
        "duration_hours": 6,
        "interval_days": 14,
        "search_hours": 12,
        "cutoff_utc": "",
        "label": "17–30 июня 2024",
        "group": "full",
    },
}


def demo_form(name):
    item = DEMOS[name]
    return {
        "mode": item["mode"],
        "start_utc": item["start_utc"],
        "duration_hours": item["duration_hours"],
        "search_hours": item["search_hours"],
        "interval_days": item["interval_days"],
        "cutoff_utc": item["cutoff_utc"],
        "refresh": "",
        "freeze": "",
    }


def demos_in_group(group):
    return [(key, item) for key, item in DEMOS.items() if item.get("group") == group]


def js_demo_fields():
    fields = ("mode", "start_utc", "duration_hours", "interval_days", "search_hours", "cutoff_utc")
    out = {}
    for key, item in DEMOS.items():
        out[key] = {name: item[name] for name in fields}
    return out
