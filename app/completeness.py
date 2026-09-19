SKIP_REASONS = {"", "ok", "нет", "n/a", "-", "none"}

REASON_RULES = (
    (
        "протонного потока",
        "Есть прогноз радиации: солнечные частицы (протоны) от NOAA SWPC.",
        "Нет прогноза радиации (солнечные частицы) на это окно.",
    ),
    (
        "есть прогнозы swpc",
        "Есть прогноз радиации от NOAA SWPC.",
        "",
    ),
    (
        "прогнозы kp",
        "Есть прогноз геомагнитной обстановки (индекс Kp).",
        "Нет прогноза геомагнитной обстановки на это окно.",
    ),
    (
        "метеорн",
        "Есть сведения об обломках и метеорных потоках.",
        "Нет сведений об обломках и метеорных потоках.",
    ),
    (
        "данных sep",
        "Есть данные по радиации.",
        "Нет данных по радиации (солнечные частицы).",
    ),
    (
        "только внешний прогноз",
        "Оценка только по чужому прогнозу, без измерений.",
        "",
    ),
)


def plain_reason(text):
    raw = " ".join(str(text or "").split())
    if not raw or raw.lower() in SKIP_REASONS:
        return ""
    key = raw.lower()
    for needle, yes, no in REASON_RULES:
        if needle not in key:
            continue
        if no and key.startswith("нет"):
            return no
        return yes
    if len(raw) <= 80 and (key.startswith("есть") or key.startswith("нет")):
        return raw
    return ""


def completeness_note(completeness, critical_missing, reasons=None):
    try:
        value = float(completeness if completeness is not None else 0)
    except (TypeError, ValueError):
        value = 0.0
    if critical_missing or value <= 0:
        hole = (
            "Дыра — нет данных по радиации на эти сутки. "
            "Пустое место не значит, что безопасно."
        )
    elif value < 1:
        hole = "Частичная дыра — известны не все данные по радиации и геомагнетизму."
    else:
        hole = "Дыры нет: данные по радиации и геомагнетизму на эти сутки есть."
    extras = []
    for item in reasons or []:
        plain = plain_reason(item)
        if plain and plain not in extras and plain not in hole:
            extras.append(plain)
    if extras:
        return hole + " " + " ".join(extras)
    return hole


def window_completeness_note(window):
    window = window or {}
    reasons = [
        (window.get("sep") or {}).get("confidence"),
        (window.get("geomagnetic") or {}).get("confidence"),
        (window.get("conjunction") or {}).get("confidence"),
    ]
    return completeness_note(
        window.get("completeness"),
        window.get("critical_missing"),
        reasons,
    )
