import re

KP_FORECAST = re.compile(r"kp\s*=\s*([\d.]+)", re.I)

KIND_PLAIN = {
    "external_forecast": "Чужой прогноз",
    "observation": "Измерение",
    "team_calc": "Наш расчёт",
    "derived": "Наш расчёт",
}

SOURCE_PLAIN = {
    "test_swpc": "Тестовый прогноз NOAA SWPC",
    "noaa_swpc": "Прогноз NOAA SWPC",
    "swpc_3day": "Прогноз NOAA SWPC на трое суток",
    "swpc_geomag": "Геомагнитный прогноз NOAA SWPC",
    "goes_protons": "Измерения протонов GOES",
    "goes_sgps": "Измерения GOES-R",
    "swpc_kp": "Индекс Kp NOAA SWPC",
    "nasa_donki": "Уведомления NASA DONKI",
    "donki_notifications": "Уведомления NASA DONKI",
    "donki_cme": "Каталог выбросов NASA DONKI",
    "socrates": "Каталог сближений SOCRATES",
    "orbit": "Орбита МКС",
    "iss_gp_history": "Архив орбиты МКС",
    "planner_api": "ВКД-планировщик",
    "spacetrack_tle": "Орбита МКС, Space-Track",
    "celestrak_iss": "Орбита МКС, CelesTrak",
}

PHRASES = (
    ("протонный флюкс <10 pfu (normal)", "Поток протонов ниже 10 единиц. Это спокойный уровень, не радиационная буря."),
    ("протонный флюкс", "Поток протонов ниже порога бури. Это спокойный уровень."),
    ("протонный поток на нормальном уровне", "Радиация в норме: поток солнечных частиц не повышен."),
    ("прогноз swpc s1 or greater", "Прогноз радиационной бури от NOAA SWPC."),
    ("поток протонов goes", "Измерение потока солнечных частиц со спутника GOES."),
    ("ряд goes не покрывает окно", "Измерений GOES на это окно нет."),
    ("поток выше порога s", "В прогнозе SWPC поток выше спокойного уровня."),
    ("kp / шкала g", "Прогноз геомагнитной обстановки на трое суток."),
    ("текущий estimated kp", "Текущий индекс геомагнитной активности (Kp)."),
    ("socrates отключён", "Каталог сближений в историческом режиме не используется."),
    ("socrates недоступен", "Каталог сближений недоступен."),
    ("сближений iss в окне", "Крупных сближений с МКС в этом окне нет."),
    ("вероятность strong–extreme storm", "Вероятность сильной геомагнитной бури."),
    ("вероятность strong-extreme storm", "Вероятность сильной геомагнитной бури."),
    ("ap из geomag forecast", "Индекс геомагнитной активности из прогноза NOAA SWPC."),
    ("прогноз swpc r3 or greater", "Прогноз сильного радиозатмения от NOAA SWPC."),
    ("прогноз swpc r1", "Прогноз радиозатмения от NOAA SWPC."),
    ("пересечение воздействий с окном", "Насколько окно пересекается с неблагоприятными условиями."),
    ("отсутствие ряда не равно s0", "Нет измерений — это не значит, что радиации нет."),
    ("нет данных ≠ нет сближения", "Нет данных не значит, что сближений нет."),
    ("не складывается с sep", "Отдельный прогноз. Не складывается с радиацией."),
    ("шкала g отдельно от sep", "Геомагнитная шкала показывается отдельно от радиации."),
    ("g3+ на сутки окна", "Сильная буря (G3 и выше) на сутки этого окна."),
    ("это не отсутствие сближений", "Это не значит, что сближений нет. Исторический каталог не подменяется текущим."),
    ("прокси обстановки, не доза", "Это оценка обстановки, не доза в скафандре."),
)

RULE_PHRASES = (
    ("sep.threshold.normal", "Спокойный уровень радиации"),
    ("sep.threshold.s1", "Порог радиационной бури"),
    ("sep.threshold", "Порог радиации"),
    ("неполнота наблюдения", "Неполное измерение"),
    ("отказ источника не all-clear", "Сбой источника — это не «всё спокойно»"),
    ("t4: не смешивать эпоху каталога", "Нельзя подставлять сегодняшний каталог в прошлое"),
    ("observed s-storm", "В прогнозе отмечена радиационная буря"),
    ("planetary k-index", "Планетарный индекс геомагнитной активности"),
    ("в сводку sep не входит", "В оценку радиации не входит"),
)


def _apply(text, rules):
    raw = " ".join(str(text or "").split())
    if not raw:
        return ""
    key = raw.lower()
    for needle, label in rules:
        if needle in key:
            return label
    return raw


def plain_kind(kind):
    key = str(kind or "").strip().lower()
    return KIND_PLAIN.get(key) or "Чужой прогноз"


def plain_source(source):
    parts = []
    for item in str(source or "").replace(";", ",").split(","):
        key = item.strip()
        if not key:
            continue
        parts.append(SOURCE_PLAIN.get(key, SOURCE_PLAIN.get(key.lower(), key)))
    return ", ".join(parts)


def plain_phrase(text):
    mapped = _apply(text, PHRASES)
    raw = " ".join(str(text or "").split())
    if mapped != raw:
        return mapped
    match = KP_FORECAST.search(raw)
    if match and "g1" in raw.lower():
        return "Прогноз геомагнитной активности: Kp {0}, ниже уровня бури.".format(match.group(1))
    return raw


def plain_rule(text):
    raw = " ".join(str(text or "").split())
    if not raw:
        return ""
    mapped = _apply(raw, RULE_PHRASES)
    if mapped != raw:
        return mapped
    if "." in raw and " " not in raw:
        return ""
    return raw


def plain_evidence_item(item):
    item = dict(item or {})
    kind = item.get("kind") or item.get("provenance") or item.get("provenance_type")
    title = item.get("title") or item.get("statement") or ""
    detail = item.get("detail") or item.get("rule_description") or ""
    source = item.get("source_id") or ", ".join(item.get("source_ids") or [])
    rule = item.get("rule") or item.get("rule_id") or ""
    item["kind"] = "external_forecast" if (kind or "").lower() not in KIND_PLAIN else kind
    item["kind_label"] = plain_kind(kind)
    item["title"] = plain_phrase(title) or title
    item["detail"] = plain_phrase(detail)
    item["source_id"] = plain_source(source) or source
    item["rule"] = plain_rule(rule)
    return item
