from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal

ALGO_VERSION = "0.1.0"


class Provenance(str, Enum):
    """Откуда взялась величина. В UI - три разных цвета (О4)."""
    OBSERVATION = "observation"              # измерено прибором
    EXTERNAL_FORECAST = "external_forecast"  # чужой прогноз (SWPC, ENLIL)
    DERIVED = "derived"                      # наш расчёт


class Grade(str, Enum):
    """Четырёхзначная оценка. INSUFFICIENT_DATA - не синоним BENIGN."""
    BENIGN = "benign"
    ELEVATED = "elevated"
    ADVERSE = "adverse"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class TimeRange:
    """Временной интервал."""
    start: datetime  # tz-aware UTC
    end: datetime    # tz-aware UTC

    def __post_init__(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("TimeRange требует tz-aware datetime")
        if self.start >= self.end:
            raise ValueError(f"start должен быть раньше end: {self.start} >= {self.end}")

    def overlaps(self, other: TimeRange) -> bool:
        """Проверяет пересечение с другим интервалом."""
        return self.start < other.end and other.start < self.end

    def overlap_minutes(self, other: TimeRange) -> float:
        """Возвращает длительность пересечения в минутах."""
        if not self.overlaps(other):
            return 0.0
        overlap_start = max(self.start, other.start)
        overlap_end = min(self.end, other.end)
        return (overlap_end - overlap_start).total_seconds() / 60.0

    @property
    def duration_hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0


def union_overlap_minutes(intervals, window: "TimeRange") -> float:
    """Минуты окна, покрытые ОБЪЕДИНЕНИЕМ интервалов.

    Сумма пересечений считает одно и то же время несколько раз: три выпуска
    прогноза на один слот давали 1080 «неблагоприятных минут» в окне на 360.
    Объединение не может превысить длину окна — это инвариант, его
    проверяет тест.
    """
    clipped = []
    for iv in intervals:
        start = max(iv.start, window.start)
        end = min(iv.end, window.end)
        if end > start:
            clipped.append((start, end))
    clipped.sort()
    total = 0.0
    cur_start = cur_end = None
    for start, end in clipped:
        if cur_end is None or start > cur_end:
            if cur_end is not None:
                total += (cur_end - cur_start).total_seconds()
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    if cur_end is not None:
        total += (cur_end - cur_start).total_seconds()
    return total / 60.0


@dataclass(frozen=True)
class Observation:
    """Центральный тип: всё, что пришло извне.
    Измерения, чужие прогнозы и наши расчёты - один тип, разные provenance.
    """
    # что
    quantity: str        # каноническое имя: "proton_flux_gt10mev"
    value: float | None  # None допустим только для событийных записей
    unit: str            # "pfu", "dimensionless", "deg", "m^-2 h^-1"

    # когда: три РАЗНЫХ времени, никогда не схлопывать
    valid_from: datetime
    valid_to: datetime | None  # None = мгновенное значение
    issued_at: datetime        # главное поле для replay
    retrieved_at: datetime
    issued_at_inferred: bool = False  # True = вывели сами

    # откуда
    source_id: str = ""       # "noaa_swpc.goes_proton_json"
    source_version: str = ""  # версия продукта: "v3-0-2"
    authority: str = ""       # "noaa_swpc_operational" | "nasa_ccmc_research"
    provenance: Provenance = Provenance.OBSERVATION
    raw_ref: str = ""         # ключ сырого снимка в raw_store
    source_url: str = ""      # для кнопки «первоисточник» в UI

    # дедупликация
    dedup_key: str = ""          # "WARK05:2265" или quantity+valid_from
    event_id: str | None = None  # связь с SpaceWeatherEvent
    version: int = 1             # для перевыпущенных записей

    # сырые поля, не лёгшие в схему
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        """Проверяет, что времена tz-aware UTC."""
        for dt_field, dt_value in [
            ("valid_from", self.valid_from),
            ("valid_to", self.valid_to),
            ("issued_at", self.issued_at),
            ("retrieved_at", self.retrieved_at),
        ]:
            if dt_value is not None and dt_value.tzinfo is None:
                raise ValueError(f"{dt_field} должен быть tz-aware, получен naive datetime")


@dataclass(frozen=True)
class SpaceWeatherEvent:
    """Группа связанных записей. Считается РАЗ (требование Т3)."""
    event_id: str
    kind: Literal["flare", "cme", "sep", "geomagnetic_storm", "radio_blackout"]
    onset: datetime | None
    onset_uncertainty_minutes: float | None  # нет точного времени - интервал
    expected_end: datetime | None
    peak_scale: str | None  # "S2", "G5", "X5.4"
    linked_event_ids: tuple[str, ...] = ()
    observation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrajectorySample:
    """Одна точка траектории МКС. Шаг 60 с для окна до 8 ч."""
    t: datetime
    lat_deg: float
    lon_deg: float
    alt_km: float
    geomag_lat_deg: float  # геомагнитная широта: порог обрезания и граница овала
    in_polar_cap: bool     # выше Kp-зависимой границы (на МКС почти всегда False)
    in_saa: bool           # Южно-Атлантическая аномалия
    in_eclipse: bool
    velocity_eci_km_s: tuple[float, float, float]   # для ram/wake


@dataclass(frozen=True)
class OrbitSource:
    """Откуда взята орбита. Показывается в UI целиком (Т2)."""
    provider: Literal["celestrak_gp", "spacetrack_gp_history"]
    epoch: datetime                 # эпоха элементов
    creation_date: datetime | None  # когда опубликованы
    age_hours_at_window: float      # давность относительно окна ВКД
    is_reconstruction: bool         # True = не подтвердили доступность на as_of
    tle_line1: str
    tle_line2: str
    gp_id: str | None = None


@dataclass(frozen=True)
class Evidence:
    """Одно звено цепочки доказательств. Это то, что открывается по клику."""
    statement: str         # "Поток >10 МэВ достиг 74 pfu"
    rule_id: str           # "sep.threshold.s1" - какое правило сработало
    rule_description: str  # человеческим языком
    provenance: Provenance
    value: float | None = None
    unit: str = ""
    source_ids: tuple[str, ...] = ()
    observations: tuple[Observation, ...] = ()


@dataclass(frozen=True)
class FactorAssessment:
    """Вывод одного механизма по одному окну."""
    factor_id: str          # "radiation_sep", "mmod_meteor", "lighting"
    grade: Grade
    coverage: float         # 0..1, полнота данных
    confidence: Literal["low", "medium", "high"]
    confidence_reason: str  # от чего зависит уверенность
    adverse_minutes: float  # сколько минут окна неблагоприятны
    adverse_intervals: tuple[TimeRange, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class WindowAssessment:
    """Одно окно ВКД целиком. Сводного числа риска НЕТ."""
    window: TimeRange
    factors: tuple[FactorAssessment, ...]
    orbit_source: OrbitSource | None  # None = элементов к as_of нет; заглушек не рисуем
    trajectory_summary: dict = field(default_factory=dict)  # САА, тень, макс. геомагн. широта


@dataclass(frozen=True)
class PlanningRequest:
    """Всё состояние запроса. Глобальных переменных нет (Т6)."""
    request_id: str
    window_start: datetime
    duration_hours: float     # 1..8
    search_span_hours: float  # до 24
    as_of: datetime           # = now для live и разбора
    mode: Literal["live", "historical_review", "strict_replay"]
    disabled_sources: frozenset[str] = frozenset()  # для демо отказов
    algo_version: str = ALGO_VERSION

    def __post_init__(self):
        if self.window_start.tzinfo is None or self.as_of.tzinfo is None:
            raise ValueError("PlanningRequest требует tz-aware datetime")
        if not (1.0 <= self.duration_hours <= 8.0):
            raise ValueError(f"duration_hours должна быть 1-8, получено {self.duration_hours}")
        if not (0.0 <= self.search_span_hours <= 24.0):
            raise ValueError(f"search_span_hours должна быть 0-24, получено {self.search_span_hours}")

    @property
    def window_end(self) -> datetime:
        from datetime import timedelta
        return self.window_start + timedelta(hours=self.duration_hours)

    @property
    def window(self) -> TimeRange:
        return TimeRange(start=self.window_start, end=self.window_end)
