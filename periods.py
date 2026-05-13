"""Helpers de période pour le dashboard. Tout est calculé en Europe/Paris."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

PARIS = ZoneInfo("Europe/Paris")

PRESETS = ["Mois en cours", "Mois précédent", "Année en cours", "Personnalisé"]


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def _today() -> date:
    from datetime import datetime
    return datetime.now(PARIS).date()


def current_month(today: date | None = None) -> Period:
    t = today or _today()
    start = t.replace(day=1)
    return Period(start=start, end=t, label="Mois en cours")


def previous_month(today: date | None = None) -> Period:
    t = today or _today()
    first_this_month = t.replace(day=1)
    end_prev = first_this_month - timedelta(days=1)
    start_prev = end_prev.replace(day=1)
    return Period(start=start_prev, end=end_prev, label="Mois précédent")


def current_year(today: date | None = None) -> Period:
    t = today or _today()
    return Period(start=t.replace(month=1, day=1), end=t, label="Année en cours")


def custom(start: date, end: date) -> Period:
    if end < start:
        start, end = end, start
    return Period(start=start, end=end, label="Personnalisé")


def from_preset(name: str, custom_range: tuple[date, date] | None = None) -> Period:
    if name == "Mois en cours":
        return current_month()
    if name == "Mois précédent":
        return previous_month()
    if name == "Année en cours":
        return current_year()
    if name == "Personnalisé" and custom_range:
        return custom(*custom_range)
    return current_month()


def previous_comparable(period: Period) -> Period:
    """Période immédiatement précédente, même durée (pour comparaison)."""
    duration = period.end - period.start
    prev_end = period.start - timedelta(days=1)
    prev_start = prev_end - duration
    return Period(start=prev_start, end=prev_end, label=f"Avant {period.label.lower()}")


def previous_year_same_period(period: Period) -> Period:
    """Même période un an avant."""
    return Period(
        start=period.start - relativedelta(years=1),
        end=period.end - relativedelta(years=1),
        label=f"{period.label} N-1",
    )
