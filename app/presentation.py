"""User-facing copy. Add a needle here when a new source introduces jargon."""

from __future__ import annotations

import json
import re

SKIP_REASONS = ("", "ok", "нет", "n/a", "-", "none")

REASON_RULES = (
    ("протонного потока", "Есть прогноз радиации: солнечные частицы (протоны) от NOAA SWPC.", "Нет прогноза радиации (солнечные частицы) на это окно."),
    ("есть прогнозы swpc", "Есть прогноз радиации от NOAA SWPC.", ""),
    ("прогнозы kp", "Есть прогноз геомагнитной обстановки (индекс Kp).", "Нет прогноза геомагнитной обстановки на это окно."),
    ("метеорн", "Есть сведения об обломках и метеорных потоках.", "Нет сведений об обломках и метеорных потоках."),
    ("данных sep", "Есть данные по радиации.", "Нет данных по радиации (солнечные частицы)."),
    ("только внешний прогноз", "Оценка только по чужому прогнозу, без измерений.", ""),
)

KIND_LABELS = {
    "external_forecast": "Чужой прогноз",
    "observation": "Измерение",
    "team_calc": "Наш расчёт",
    "derived": "Наш расчёт",
}

SOURCE_LABELS = {
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

EVIDENCE_PHRASES = (
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

LEVEL_WORDS = {
    "none": "спокойно",
    "watch": "нужно внимание",
    "warning": "опасно",
    "high": "очень опасно",
    "unknown": "нет данных",
}

KP_FORECAST = re.compile(r"kp\s*=\s*([\d.]+)", re.I)


def _normalize(text):
    return " ".join(str(text or "").split())


def _first_match(text, rules):
    key = text.lower()
    for needle, label in rules:
        if needle in key:
            return label
    return text


class PhraseBook:
    """Plain-language labels for completeness, evidence, sources, and levels."""

    def reason(self, text):
        raw = _normalize(text)
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

    def completeness_note(self, completeness, critical_missing, reasons=None):
        try:
            value = float(completeness if completeness is not None else 0)
        except (TypeError, ValueError):
            value = 0.0
        if critical_missing or value <= 0:
            hole = "Дыра — нет данных по радиации на эти сутки. Пустое место не значит, что безопасно."
        elif value < 1:
            hole = "Частичная дыра — известны не все данные по радиации и геомагнетизму."
        else:
            hole = "Дыры нет: данные по радиации и геомагнетизму на эти сутки есть."
        extras = []
        for item in reasons or []:
            plain = self.reason(item)
            if plain and plain not in extras and plain not in hole:
                extras.append(plain)
        if extras:
            return hole + " " + " ".join(extras)
        return hole

    def window_completeness_note(self, window):
        window = window or {}
        reasons = [
            (window.get("sep") or {}).get("confidence"),
            (window.get("geomagnetic") or {}).get("confidence"),
            (window.get("conjunction") or {}).get("confidence"),
        ]
        return self.completeness_note(
            window.get("completeness"),
            window.get("critical_missing"),
            reasons,
        )

    def kind(self, kind):
        key = str(kind or "").strip().lower()
        return KIND_LABELS.get(key) or "Чужой прогноз"

    def source(self, source):
        parts = []
        for item in str(source or "").replace(";", ",").split(","):
            key = item.strip()
            if not key:
                continue
            parts.append(SOURCE_LABELS.get(key, SOURCE_LABELS.get(key.lower(), key)))
        return ", ".join(parts)

    def phrase(self, text):
        raw = _normalize(text)
        if not raw:
            return ""
        mapped = _first_match(raw, EVIDENCE_PHRASES)
        if mapped != raw:
            return mapped
        match = KP_FORECAST.search(raw)
        if match and "g1" in raw.lower():
            return "Прогноз геомагнитной активности: Kp {0}, ниже уровня бури.".format(match.group(1))
        return raw

    def rule(self, text):
        raw = _normalize(text)
        if not raw:
            return ""
        mapped = _first_match(raw, RULE_PHRASES)
        if mapped != raw:
            return mapped
        if "." in raw and " " not in raw:
            return ""
        return raw

    def evidence_item(self, item):
        item = dict(item or {})
        kind = item.get("kind") or item.get("provenance") or item.get("provenance_type")
        title = item.get("title") or item.get("statement") or ""
        detail = item.get("detail") or item.get("rule_description") or ""
        source = item.get("source_id") or ", ".join(item.get("source_ids") or [])
        rule = item.get("rule") or item.get("rule_id") or ""
        item["kind"] = kind if (kind or "").lower() in KIND_LABELS else "external_forecast"
        item["kind_label"] = self.kind(kind)
        item["title"] = self.phrase(title) or title
        item["detail"] = self.phrase(detail)
        item["source_id"] = self.source(source) or source
        item["rule"] = self.rule(rule)
        return item

    def client_bundle(self):
        return {
            "kinds": KIND_LABELS,
            "sources": SOURCE_LABELS,
            "phrases": [{"needle": needle, "label": label} for needle, label in EVIDENCE_PHRASES],
            "rules": [{"needle": needle, "label": label} for needle, label in RULE_PHRASES],
            "reasons": [
                {"needle": needle, "yes": yes, "no": no}
                for needle, yes, no in REASON_RULES
            ],
            "skipReasons": list(SKIP_REASONS),
            "levels": LEVEL_WORDS,
        }

    def client_json(self):
        return json.dumps(self.client_bundle(), ensure_ascii=False, separators=(",", ":"))


copy = PhraseBook()
