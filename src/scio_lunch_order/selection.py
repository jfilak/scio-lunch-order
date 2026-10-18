"""Turns the ``order`` command line arguments into a dish of a parsed menu.

``--day`` accepts an ISO date (``2026-10-16``), a numeric Czech date
(``16.10.2026``) or a label like the one the site shows (``pátek 16. října``,
``16. října``).  Labels are matched by their date, never by their text: the
site calls tomorrow ``zítra, 13. října`` instead of using its weekday.

``--item`` is the dish number shown in front of the dish (``3.``, ``6.``).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from .models import Day, FoodItem, Menu

# Genitive, as in "16. října".
MONTHS = (
    "ledna",
    "února",
    "března",
    "dubna",
    "května",
    "června",
    "července",
    "srpna",
    "září",
    "října",
    "listopadu",
    "prosince",
)
WEEKDAYS = ("pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle")
# Words the site puts in place of the weekday.
RELATIVE_DAYS = ("dnes", "zítra")

_ISO_RE = re.compile(r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})")
_NUMERIC_RE = re.compile(
    r"(?P<day>\d{1,2})\.\s*(?P<month>\d{1,2})(?:\.\s*(?P<year>\d{4})?)?"
)
_LABEL_RE = re.compile(
    r"(?:(?P<weekday>[^\W\d_]+)\s*,?\s+)?"
    r"(?P<day>\d{1,2})\.?\s*(?P<month>[^\W\d_]+)"
    r"(?:\s+(?P<year>\d{4}))?"
)
_ITEM_RE = re.compile(r"(\d+)\.?")


class SelectionError(Exception):
    """The requested dish is not on the menu, or cannot be ordered."""


@dataclass(frozen=True)
class DaySpec:
    """A day given on the command line; the year is optional."""

    text: str
    day: int
    month: int
    year: int | None = None
    weekday: int | None = None  # as date.weekday(): 0 is Monday

    def matches(self, value: date) -> bool:
        return (value.day, value.month) == (self.day, self.month) and (
            self.year is None or self.year == value.year
        )


def parse_day_spec(text: str) -> DaySpec:
    """``2026-10-16``, ``16.10.2026``, ``pátek 16. října`` -> :class:`DaySpec`."""
    cleaned = _normalize(text)
    weekday: int | None = None

    match = _ISO_RE.fullmatch(cleaned) or _NUMERIC_RE.fullmatch(cleaned)
    if match:
        month = int(match.group("month"))
    else:
        match = _LABEL_RE.fullmatch(cleaned)
        if match is None:
            raise SelectionError(
                f"{text!r} is not a day -- use 2026-10-16, 16.10.2026 or 'pátek 16. října'"
            )
        month = _lookup(match.group("month"), MONTHS, "month") + 1
        if match.group("weekday") and _fold(match.group("weekday")) not in _folded(RELATIVE_DAYS):
            weekday = _lookup(match.group("weekday"), WEEKDAYS, "weekday")

    day = int(match.group("day"))
    year = int(match.group("year")) if match.group("year") else None
    try:
        # 2000 is a leap year, so "29. února" without a year is accepted.
        date(year or 2000, month, day)
    except ValueError as exc:
        raise SelectionError(f"{text!r} is not a valid date") from exc
    return DaySpec(text=text, day=day, month=month, year=year, weekday=weekday)


def parse_item_spec(text: str) -> str:
    """``3`` or ``3.`` -> ``"3"``, comparable with :attr:`FoodItem.number`."""
    match = _ITEM_RE.fullmatch(_normalize(text))
    if match is None:
        raise SelectionError(f"{text!r} is not a dish number such as 3 or 6")
    return str(int(match.group(1)))


def find_item(menu: Menu, day_spec: DaySpec, number: str) -> tuple[Day, FoodItem]:
    """The day and the dish the command line asks for."""
    days = [day for day in menu.days if day.date and day_spec.matches(day.date)]
    if not days:
        available = ", ".join(day.date.isoformat() for day in menu.days if day.date)
        raise SelectionError(
            f"{day_spec.text!r} is not on the menu (available: {available or 'nothing'})"
        )
    if len(days) > 1:
        raise SelectionError(f"{day_spec.text!r} matches several days -- add the year")

    day = days[0]
    if day_spec.weekday is not None and day.date.weekday() != day_spec.weekday:
        raise SelectionError(
            f"{day.date.isoformat()} is {WEEKDAYS[day.date.weekday()]}, "
            f"not {WEEKDAYS[day_spec.weekday]}"
        )

    items = [item for item in day.items if item.number == number]
    if not items:
        available = ", ".join(item.number for item in day.items if item.number)
        raise SelectionError(
            f"there is no dish {number} on {describe_day(day)} "
            f"(available: {available or 'nothing'})"
        )
    if len(items) > 1:
        raise SelectionError(f"dish {number} is listed twice on {describe_day(day)}")
    return day, items[0]


def ensure_orderable(day: Day, item: FoodItem) -> None:
    """Refuse an order the ``order`` command cannot place safely.

    Call it only for a dish that is not ordered yet.
    """
    others = [other.number or "?" for other in day.ordered_items if other is not item]
    if others:
        raise SelectionError(
            f"{describe_day(day)} already has dish {', '.join(others)} ordered -- "
            "cancel it on the site first (cancelling is not supported yet)"
        )
    if not item.can_order:
        raise SelectionError(f"dish {item.number} on {describe_day(day)} cannot be ordered")


def czech_date(value: date) -> str:
    """``date(2026, 10, 16)`` -> ``16. října 2026``, as the site writes it."""
    return f"{value.day}. {MONTHS[value.month - 1]} {value.year}"


def describe_day(day: Day) -> str:
    if day.date is None:
        return day.label or "?"
    return f"{day.label} ({day.date.isoformat()})"


def _lookup(word: str, names: tuple[str, ...], kind: str) -> int:
    """Index of ``word`` in ``names``, ignoring case and diacritics."""
    try:
        return _folded(names).index(_fold(word))
    except ValueError:
        raise SelectionError(f"unknown {kind} {word!r}") from None


def _folded(names: tuple[str, ...]) -> list[str]:
    return [_fold(name) for name in names]


def _fold(text: str) -> str:
    """``Října`` -> ``rijna``: lets ``patek 16. rijna`` be typed on any keyboard."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
