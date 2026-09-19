# VKD ISS Advisor

Исследовательский прототип для КосмоХакатона: аналитик задаёт окно ВКД, сервис сравнивает внешнюю обстановку на траектории МКС.

Это не допуск к реальному выходу.

## Публичный стенд

https://andromedasmart.github.io/vkd-iss-advisor/

Онлайн-режим ходит в API http://46.29.164.87:8000/ v0.2.0 (`POST /api/assess-window`, `GET /api/data-sources-status`). Пустые сутки API заполняются локальным архивом NCEI/DONKI. Можно выгрузить сравнение в JSON и CSV.

## Что умеет прототип

- Текущий режим: GOES ≥10 МэВ, NOAA Scales, Kp, 3-day forecast, TLE МКС (SGP4), SOCRATES.
- Исторический replay (1 апреля — 31 июля 2024): 3-day forecast SWPC с `Issued` ≤ отсечению; орбита МКС из GP_HISTORY (`CREATION_DATE` ≤ отсечения). Текущие TLE и SOCRATES в прошлое не подставляются. Дни без файлов — дыра, не all-clear.
- Два механизма: SEP и сближения / MMOD. Шкала G показывается отдельно и не суммируется с SEP.
- Сравнение окон одинаковой длительности; равнозначность и отказ от рекомендации при дыре в данных.
- Готовые демо: буря 10–13 мая, тихий интервал 18–22 июня, дыра 1–7 июня, плотные участки 1–14 мая и 17–30 июня.
- Выгрузка JSON и CSV.

## Запуск

Нужен Python 3.8+.

```bash
cd ~/Projects/vkd-iss-advisor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

Локально: http://127.0.0.1:8001

Офлайн-replay по архиву: `VKD_LOCAL_ARCHIVES=1`.

JSON расчёта: `GET /api/evaluate?mode=historical&start_utc=2024-05-10%2008:00&duration_hours=6&interval_days=4&offline=on`

Статический стенд: `python scripts/build_stand.py`.

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
| GP ISS 25544 | Space-Track GP_HISTORY | историческая орбита |
| Сближения | CelesTrak SOCRATES Plus | внешний прогноз, только current |

Локальные копии лежат в `data/archives/`. Если задан `VKD_DATA_DIR`, сравнение читает его в первую очередь. Столбцы таблицы появляются только когда в интервале есть соответствующие данные.
