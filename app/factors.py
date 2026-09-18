from __future__ import annotations

from datetime import timedelta

from app.timeutil import iso, overlap_minutes

LEVELS = ("none", "watch", "warning", "high", "unknown")
LEVEL_RANK = {"none": 0, "watch": 1, "warning": 2, "high": 3, "unknown": -1}


def s_scale_from_flux(flux):
    if flux is None:
        return None
    if flux < 10:
        return 0
    if flux < 100:
        return 1
    if flux < 1000:
        return 2
    if flux < 10000:
        return 3
    if flux < 100000:
        return 4
    return 5


def level_from_s(scale):
    if scale is None:
        return "unknown"
    if scale <= 0:
        return "none"
    if scale == 1:
        return "watch"
    if scale == 2:
        return "warning"
    return "high"


def level_from_s1_percent(pct):
    if pct is None:
        return "unknown"
    if pct < 10:
        return "none"
    if pct < 30:
        return "watch"
    if pct < 70:
        return "warning"
    return "high"


def level_from_g(g):
    if g is None:
        return "unknown"
    if g <= 0:
        return "none"
    if g == 1:
        return "watch"
    if g == 2:
        return "warning"
    return "high"


def max_level(a, b):
    if a == "unknown":
        return b
    if b == "unknown":
        return a
    return a if LEVEL_RANK[a] >= LEVEL_RANK[b] else b


def score_sep(window_start, window_end, forecast, protons, now):
    """SEP mechanism. Geomagnetic data must not be passed in here."""
    evidence = []
    obs_level = "unknown"
    fcst_level = "unknown"
    overlap_warn = 0.0
    max_flux = None
    max_s = None
    used_obs = False
    used_fcst = False

    if protons and protons.ok and protons.payload:
        in_window = [
            row
            for row in protons.payload
            if window_start <= row["time"] <= window_end
        ]
        # Future part of the window cannot use observations after "now"
        if now is not None:
            in_window = [row for row in in_window if row["time"] <= now]
        if in_window:
            max_flux = max(row["flux"] for row in in_window)
            max_s = s_scale_from_flux(max_flux)
            obs_level = level_from_s(max_s)
            used_obs = True
            if max_s and max_s >= 1:
                overlap_warn += overlap_minutes(window_start, window_end, in_window[0]["time"], in_window[-1]["time"])
            evidence.append(
                {
                    "kind": "observation",
                    "title": "Поток протонов GOES ≥10 МэВ",
                    "value": "{0:.3g} p/(cm² s sr)".format(max_flux),
                    "detail": "S{0} по порогам NOAA; это прокси обстановки, не доза в скафандре".format(max_s),
                    "source_id": protons.source_id,
                    "time": iso(in_window[-1]["time"]),
                    "rule": "S0<10; S1≥10; S2≥100; S3≥1000",
                }
            )
        elif window_end <= (now or window_end) and window_end < protons.payload[0]["time"]:
            evidence.append(
                {
                    "kind": "observation",
                    "title": "Ряд GOES не покрывает окно",
                    "value": "нет точек",
                    "detail": "Отсутствие ряда не равно S0",
                    "source_id": protons.source_id,
                    "time": iso(protons.published_at),
                    "rule": "неполнота наблюдения",
                }
            )

    if forecast and forecast.ok and forecast.payload:
        used_fcst = True
        s_probs = forecast.payload.get("s1_probs") or []
        overlapping = [
            item
            for item in s_probs
            if overlap_minutes(window_start, window_end, item["start"], item["end"]) > 0
        ]
        if overlapping:
            worst_pct = max(item["s1_percent"] for item in overlapping)
            fcst_level = level_from_s1_percent(worst_pct)
            for item in overlapping:
                minutes = overlap_minutes(window_start, window_end, item["start"], item["end"])
                if item["s1_percent"] >= 30:
                    overlap_warn += minutes
            evidence.append(
                {
                    "kind": "external_forecast",
                    "title": "Прогноз SWPC S1 or greater",
                    "value": "{0}%".format(worst_pct),
                    "detail": forecast.payload.get("rationale_s") or "Вероятность радиационной бури S1+ на сутки окна",
                    "source_id": forecast.source_id,
                    "time": iso(forecast.published_at),
                    "rule": "<10% none; 10–29 watch; 30–69 warning; ≥70 high",
                }
            )
        if forecast.payload.get("observed_s_storm"):
            obs_level = max_level(obs_level, "warning")
            evidence.append(
                {
                    "kind": "observation",
                    "title": "В выпуске SWPC: поток выше порога S",
                    "value": "above S-scale",
                    "detail": "Это наблюдение из датированного продукта, не расчёт команды",
                    "source_id": forecast.source_id,
                    "time": iso(forecast.published_at),
                    "rule": "observed S-storm в 3-day forecast",
                }
            )

    if not used_obs and not used_fcst:
        level = "unknown"
        confidence = "нет данных SEP"
    elif not used_obs and used_fcst:
        level = fcst_level
        confidence = "только внешний прогноз"
    elif used_obs and not used_fcst:
        level = obs_level
        confidence = "только наблюдение, без прогноза на горизонт окна"
    else:
        level = max_level(obs_level, fcst_level)
        confidence = "наблюдение и внешний прогноз; связанные сигналы не суммируются, берётся максимум группы SEP"

    return {
        "mechanism": "sep",
        "title": "Солнечные энергичные частицы",
        "level": level,
        "confidence": confidence,
        "overlap_minutes": round(overlap_warn, 1),
        "max_flux": max_flux,
        "max_s": max_s,
        "incomplete": level == "unknown",
        "evidence": evidence,
        "applies_to": "окно ВКД",
        "limit": "Прокси потока на GOES, не эквивалентная доза экипажа",
    }


def score_geomagnetic(window_start, window_end, forecast, kp_now):
    """Separate from SEP. Never added into SEP score."""
    evidence = []
    level = "unknown"
    overlap_warn = 0.0
    max_g = 0
    if forecast and forecast.ok and forecast.payload:
        bins = forecast.payload.get("kp_bins") or []
        overlapping = [
            item
            for item in bins
            if overlap_minutes(window_start, window_end, item["start"], item["end"]) > 0
        ]
        if overlapping:
            max_g = max(item["g"] for item in overlapping)
            level = level_from_g(max_g)
            for item in overlapping:
                minutes = overlap_minutes(window_start, window_end, item["start"], item["end"])
                if item["g"] >= 2:
                    overlap_warn += minutes
            worst = max(overlapping, key=lambda item: item["g"])
            evidence.append(
                {
                    "kind": "external_forecast",
                    "title": "Kp / шкала G из 3-day forecast",
                    "value": "Kp {0:.2f} (G{1})".format(worst["kp"], worst["g"]),
                    "detail": forecast.payload.get("rationale_g")
                    or "Геомагнитная буря — другое явление, не складывается с SEP",
                    "source_id": forecast.source_id,
                    "time": iso(forecast.published_at),
                    "rule": "G1 Kp=5 … G5 Kp=9; в сводку SEP не входит",
                }
            )
    if kp_now and kp_now.ok and kp_now.payload:
        recent = kp_now.payload[-1]
        evidence.append(
            {
                "kind": "observation",
                "title": "Текущий estimated Kp",
                "value": "{0:.2f}".format(recent["kp"]),
                "detail": "Наблюдение сейчас; не заменяет прогноз на окно",
                "source_id": kp_now.source_id,
                "time": iso(recent["time"]),
                "rule": "planetary K-index 1 min",
            }
        )
        if level == "unknown":
            level = level_from_g(_kp_to_g(recent["kp"]))
    if level == "unknown" and not evidence:
        return {
            "mechanism": "geomagnetic",
            "title": "Геомагнитная обстановка (не суммируется с SEP)",
            "level": "unknown",
            "confidence": "нет данных",
            "overlap_minutes": 0.0,
            "incomplete": True,
            "evidence": [],
            "applies_to": "контекст, не вторая радиационная доза",
            "limit": "G не означает S и не добавляет риск SEP автоматически",
        }
    return {
        "mechanism": "geomagnetic",
        "title": "Геомагнитная обстановка (не суммируется с SEP)",
        "level": level,
        "confidence": "шкала G отдельно от SEP",
        "overlap_minutes": round(overlap_warn, 1),
        "max_g": max_g,
        "incomplete": False,
        "evidence": evidence,
        "applies_to": "контекст работ / магнитосфера",
        "limit": "Не вероятность повреждения станции и не доза SEP",
    }


def _kp_to_g(kp):
    if kp >= 9:
        return 5
    if kp >= 8:
        return 4
    if kp >= 7:
        return 3
    if kp >= 6:
        return 2
    if kp >= 5:
        return 1
    return 0


def score_conjunctions(window_start, window_end, socrates, allowed):
    if not allowed:
        return {
            "mechanism": "conjunction",
            "title": "Сближения каталожных объектов",
            "level": "unknown",
            "confidence": "текущий каталог SOCRATES непригоден для исторического replay",
            "overlap_minutes": 0.0,
            "incomplete": True,
            "events": [],
            "evidence": [
                {
                    "kind": "external_forecast",
                    "title": "SOCRATES отключён в историческом режиме",
                    "value": "не используется",
                    "detail": "Это не отсутствие сближений. Исторический каталог не подменяется текущим.",
                    "source_id": "socrates",
                    "time": None,
                    "rule": "T4: не смешивать эпоху каталога",
                }
            ],
            "applies_to": "станция и каталожные объекты",
            "limit": "Не вероятность попадания мелкого обломка в космонавта",
        }
    if not socrates or not socrates.ok:
        return {
            "mechanism": "conjunction",
            "title": "Сближения каталожных объектов",
            "level": "unknown",
            "confidence": "каталог недоступен",
            "overlap_minutes": 0.0,
            "incomplete": True,
            "events": [],
            "evidence": [
                {
                    "kind": "external_forecast",
                    "title": "SOCRATES недоступен",
                    "value": (socrates.error if socrates else "нет источника"),
                    "detail": "Нет данных ≠ нет сближения",
                    "source_id": "socrates",
                    "time": iso(socrates.fetched_at) if socrates else None,
                    "rule": "отказ источника не all-clear",
                }
            ],
            "applies_to": "станция и каталожные объекты",
            "limit": "Не MMOD-поток",
        }

    pad = timedelta(minutes=30)
    hits = []
    for event in socrates.payload or []:
        if window_start - pad <= event["tca"] <= window_end + pad:
            hits.append(event)
    if not hits:
        evidence = [
            {
                "kind": "external_forecast",
                "title": "Сближений ISS в окне ±30 мин нет",
                "value": "0 TCA",
                "detail": "По текущему прогону SOCRATES; это не оценка мелкого мусора",
                "source_id": socrates.source_id,
                "time": iso(socrates.fetched_at),
                "rule": "пересечение TCA с окном ВКД",
            }
        ]
        return {
            "mechanism": "conjunction",
            "title": "Сближения каталожных объектов",
            "level": "none",
            "confidence": "каталог получен",
            "overlap_minutes": 0.0,
            "incomplete": False,
            "events": [],
            "evidence": evidence,
            "applies_to": "станция и каталожные объекты",
            "limit": "Не вероятность попадания мелкого обломка в космонавта",
        }

    def event_level(event):
        rng = event["min_range_km"]
        if rng < 1.0:
            return "high"
        if rng < 2.0:
            return "warning"
        if rng < 5.0:
            return "watch"
        return "none"

    closest = min(hits, key=lambda event: event["min_range_km"])
    level = event_level(closest)
    overlap = 0.0
    for event in hits:
        if event_level(event) in ("watch", "warning", "high"):
            overlap += 60.0
    evidence = []
    for event in hits[:5]:
        evidence.append(
            {
                "kind": "external_forecast",
                "title": "TCA с {0}".format(event["other_name"]),
                "value": "{0:.3f} км, Pmax={1:.2e}".format(
                    event["min_range_km"], event["max_probability"]
                ),
                "detail": "TCA {0}; относительная скорость {1:.2f} км/с. Расчёт команды — пересечение с окном, не сама вероятность.".format(
                    iso(event["tca"]), event["relative_speed_km_s"]
                ),
                "source_id": socrates.source_id,
                "time": iso(event["tca"]),
                "rule": "<5 км watch; <2 км warning; <1 км high",
            }
        )
    return {
        "mechanism": "conjunction",
        "title": "Сближения каталожных объектов",
        "level": level,
        "confidence": "SOCRATES max probability — внешняя оценка, не наша модель",
        "overlap_minutes": overlap,
        "incomplete": False,
        "events": hits,
        "closest_km": closest["min_range_km"],
        "tca": iso(closest["tca"]),
        "evidence": evidence,
        "applies_to": "станция и каталожные объекты",
        "limit": "Не вероятность попадания мелкого обломка в космонавта",
    }


def level_from_ap(ap):
    if ap is None:
        return "unknown"
    if ap < 20:
        return "none"
    if ap < 30:
        return "watch"
    if ap < 50:
        return "warning"
    return "high"


def level_from_r3_percent(pct):
    if pct is None:
        return "unknown"
    if pct < 15:
        return "none"
    if pct < 30:
        return "watch"
    if pct < 50:
        return "warning"
    return "high"


def score_radio(window_start, window_end, forecast):
    evidence = []
    level = "unknown"
    worst_r12 = None
    worst_r3 = None
    if forecast and forecast.ok and forecast.payload:
        r12 = [
            item
            for item in (forecast.payload.get("r12_probs") or [])
            if overlap_minutes(window_start, window_end, item["start"], item["end"]) > 0
        ]
        r3 = [
            item
            for item in (forecast.payload.get("r3_probs") or [])
            if overlap_minutes(window_start, window_end, item["start"], item["end"]) > 0
        ]
        if r12:
            worst_r12 = max(item["r12_percent"] for item in r12)
            level = max_level(level, level_from_s1_percent(worst_r12))
            evidence.append(
                {
                    "kind": "external_forecast",
                    "title": "Прогноз SWPC R1–R2",
                    "value": "{0}%".format(worst_r12),
                    "detail": forecast.payload.get("rationale_r") or "Вероятность радиозатмения R1–R2",
                    "source_id": forecast.source_id,
                    "time": iso(forecast.published_at),
                    "rule": "<10% none; 10–29 watch; 30–69 warning; ≥70 high",
                }
            )
        if r3:
            worst_r3 = max(item["r3_percent"] for item in r3)
            level = max_level(level, level_from_r3_percent(worst_r3))
            evidence.append(
                {
                    "kind": "external_forecast",
                    "title": "Прогноз SWPC R3 or greater",
                    "value": "{0}%".format(worst_r3),
                    "detail": "Сильное радиозатмение — связь/навигация, не доза SEP",
                    "source_id": forecast.source_id,
                    "time": iso(forecast.published_at),
                    "rule": "<15% none; 15–29 watch; 30–49 warning; ≥50 high",
                }
            )
        if forecast.payload.get("observed_r_storm"):
            level = max_level(level, "warning")
            evidence.append(
                {
                    "kind": "observation",
                    "title": "В выпуске SWPC: радиозатмение наблюдалось",
                    "value": "R observed",
                    "detail": "Наблюдение из датированного 3-day forecast",
                    "source_id": forecast.source_id,
                    "time": iso(forecast.published_at),
                    "rule": "observed radio blackout",
                }
            )
    return {
        "mechanism": "radio",
        "title": "Радиозатмения R (не суммируются с SEP)",
        "level": level,
        "confidence": "шкала R отдельно от SEP и G" if level != "unknown" else "нет данных R",
        "incomplete": level == "unknown",
        "r12_percent": worst_r12,
        "r3_percent": worst_r3,
        "evidence": evidence,
        "applies_to": "связь / навигация, не радиация экипажа",
        "limit": "R не добавляется к SEP и не означает G",
    }


def merge_geomag_product(geo, window_start, geomag):
    if not geomag or not geomag.ok or not geomag.payload:
        return geo, None, None
    from app.dataset import ap_for_day, storm_prob_for_day

    ap_row = ap_for_day(geomag.payload, window_start)
    storm = storm_prob_for_day(geomag.payload, window_start, "strong")
    ap_value = ap_row[0] if ap_row else None
    ap_kind = ap_row[1] if ap_row else None
    if ap_value is not None:
        geo["level"] = max_level(geo["level"], level_from_ap(ap_value))
        geo["incomplete"] = False
        geo["evidence"].append(
            {
                "kind": "external_forecast",
                "title": "Ap из geomag forecast ({0})".format(ap_kind),
                "value": str(ap_value),
                "detail": "Отдельный продукт SWPC; не складывается с SEP",
                "source_id": geomag.source_id,
                "time": iso(geomag.published_at),
                "rule": "<20 none; 20–29 watch; 30–49 warning; ≥50 high",
            }
        )
    if storm is not None:
        if storm >= 50:
            geo["level"] = max_level(geo["level"], "high")
        elif storm >= 25:
            geo["level"] = max_level(geo["level"], "warning")
        elif storm >= 10:
            geo["level"] = max_level(geo["level"], "watch")
        geo["incomplete"] = False
        geo["evidence"].append(
            {
                "kind": "external_forecast",
                "title": "Вероятность Strong–Extreme storm",
                "value": "{0}%".format(storm),
                "detail": "G3+ на сутки окна по geomag forecast",
                "source_id": geomag.source_id,
                "time": iso(geomag.published_at),
                "rule": "≥10 watch; ≥25 warning; ≥50 high",
            }
        )
    return geo, ap_value, storm


def score_cme(hits):
    earthward = [row for row in hits if row.get("earthward")]
    fastest = hits[0] if hits else None
    if earthward:
        fastest = max(earthward, key=lambda row: row.get("speed") or 0)
    level = "none" if hits else "unknown"
    speed = (fastest or {}).get("speed")
    if earthward:
        if speed and speed >= 1500:
            level = "high"
        elif speed and speed >= 1000:
            level = "warning"
        else:
            level = "watch"
    evidence = []
    for row in (earthward or hits)[:4]:
        lon = row.get("longitude")
        evidence.append(
            {
                "kind": "external_forecast",
                "title": "CME {0}".format(row["start"].strftime("%Y-%m-%d %H:%M")),
                "value": "{0} км/с · lon {1}°".format(row.get("speed") or "—", lon if lon is not None else "—"),
                "detail": "{0}; halfAngle {1}°; {2}".format(
                    "к Земле" if row.get("earthward") else "не earthward",
                    row.get("half_angle") or "—",
                    "submission ≤ отсечения" if row.get("submitted") else "без submissionTime",
                ),
                "source_id": "donki_cme",
                "time": iso(row.get("submitted") or row["start"]),
                "rule": "earthward: |lon| ≤ halfAngle+10; ≥1000 км/с warning; ≥1500 high",
            }
        )
    return {
        "mechanism": "cme",
        "title": "Выбросы корональной массы (DONKI)",
        "level": level,
        "confidence": "каталог CME analysis; не сумма с SEP" if hits else "нет CME в окне ±2 сут",
        "incomplete": False,
        "count": len(hits),
        "earthward": len(earthward),
        "fastest": speed,
        "evidence": evidence,
        "applies_to": "контекст прибытия возмущения, не доза",
        "limit": "Геометрия по lon/halfAngle — эвристика, не WSA-ENLIL",
    }


def score_donki(hits):
    types = []
    seen = set()
    for row in hits:
        kind = row.get("type") or "?"
        if kind not in seen:
            seen.add(kind)
            types.append(kind)
    level = "none" if hits else "unknown"
    if "SEP" in seen:
        level = "warning"
    elif "GST" in seen:
        level = "watch"
    elif hits:
        level = "watch"
    evidence = []
    for row in hits[:6]:
        evidence.append(
            {
                "kind": "external_forecast",
                "title": "{0} {1}".format(row.get("type"), row.get("id") or ""),
                "value": iso(row["issued"]),
                "detail": (row.get("body") or "").splitlines()[0][:160] if row.get("body") else "уведомление DONKI",
                "source_id": "donki_notifications",
                "time": iso(row["issued"]),
                "rule": "messageIssueTime ≤ отсечения; SEP → не ниже warning",
            }
        )
    return {
        "mechanism": "donki",
        "title": "Уведомления DONKI",
        "level": level,
        "confidence": "оперативные сообщения NASA, не модель команды" if hits else "нет уведомлений на сутки",
        "incomplete": False,
        "count": len(hits),
        "types": ", ".join(types),
        "has_sep": "SEP" in seen,
        "has_gst": "GST" in seen,
        "has_flr": "FLR" in seen,
        "evidence": evidence,
        "applies_to": "контекст оперативных алертов",
        "limit": "Текст уведомления не пересчитывается в дозу",
    }


def apply_donki_to_sep(sep, donki):
    if not donki or not donki.get("has_sep"):
        return sep
    sep["level"] = max_level(sep["level"], "warning")
    sep["incomplete"] = False
    sep["confidence"] = "DONKI SEP + " + sep["confidence"]
    sep["evidence"].extend(donki["evidence"][:2])
    return sep
