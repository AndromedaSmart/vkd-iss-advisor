# VKD ISS Advisor

Исследовательский прототип для КосмоХакатона: аналитик задаёт окно ВКД, сервис сравнивает внешнюю обстановку на траектории МКС.

Это не допуск к реальному выходу.

## Что умеет предварительный прототип

- Текущий режим: GOES ≥10 МэВ, NOAA Scales, Kp, 3-day forecast, TLE МКС (SGP4), SOCRATES.
- Исторический replay (1 мая — 30 июня 2024): 3-day forecast SWPC с `Issued` ≤ отсечению; орбита МКС из локального GP_HISTORY (`CREATION_DATE` ≤ отсечения). Текущие TLE и SOCRATES в прошлое не подставляются.
- Два механизма: SEP и сближения каталожных объектов. Шкала G показывается отдельно и не суммируется с SEP.
- Сравнение окон одинаковой длительности; равнозначность и отказ от рекомендации при дыре в данных.
- Выгрузка JSON с версией алгоритма и источниками.
- Freeze кеша и принудительное обновление.

## Запуск

Нужен Python 3.8+.

```bash
cd ~/Projects/vkd-iss-advisor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Публичный демо-стенд: https://andromedasmart.github.io/vkd-iss-advisor/

На стенде сразу открывается сравнение 10–13 мая 2024. Кнопками можно перейти к тихому интервалу 18–22 июня и к дыре покрытия 1–7 июня с DONKI.

Локально: http://127.0.0.1:8000

Демо бури: http://127.0.0.1:8000/demo/storm

JSON: `GET /api/evaluate?mode=current&duration_hours=6&search_hours=12`

## Тесты

```bash
source .venv/bin/activate
python -m pytest -q
```

## Источники

| Величина | Источник | Роль |
|---|---|---|
| Протоны ≥10 МэВ | NOAA SWPC GOES JSON | наблюдение |
| 3-day forecast S/G/R, Kp | SWPC / архив NCEI | внешний прогноз |
| Kp | SWPC planetary K-index | наблюдение |
| TLE ISS 25544 | CelesTrak GP | орбита, текущий режим |
| GP ISS 25544 | Space-Track GP_HISTORY, `data/archive/iss_gp_history_2024.json` | историческая орбита |
| Сближения | CelesTrak SOCRATES Plus | внешний прогноз, только current |

Локальные копии NCEI лежат в `data/archive/ncei/`. Встроенный набор для стенда — `data/bundle/` (geomag, DONKI, CME). Если есть `/Users/andreysorokin/Downloads/data` или `VKD_DATA_DIR`, сравнение читает его в первую очередь. Столбцы таблицы появляются только когда в интервале есть соответствующие данные. Дыра в архиве (15–31 мая, 1–15 июня 2024) не считается all-clear.

Статический стенд пересобирается так: `python scripts/build_stand.py`.
