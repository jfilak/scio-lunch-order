"""Ways of picking the dish of a day that offers more than one.

A :data:`Chooser` gets the day and those of its dishes that can be ordered,
and returns one of them, or ``None`` to order nothing that day.  ``order-all``
calls it once per such day, in menu order, and before anything is ordered --
so a chooser may keep state, e.g. to alternate meat and vegetarian dishes
over the week.

Only the interactive prompt exists for now.  A list of preferred dishes or an
AI callback deciding between meat and vegetarian are meant to be further
choosers (and may fall back on each other).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import TextIO

from .models import Day, FoodItem
from .selection import describe_day

LOG = logging.getLogger(__name__)

Chooser = Callable[[Day, list[FoodItem]], "FoodItem | None"]


def ask_user(stdin: TextIO | None = None, stderr: TextIO | None = None) -> Chooser:
    """A chooser that lists the dishes and asks for a number.

    The prompt goes to stderr, so that stdout stays clean for ``--json``.
    An empty answer (or the end of input) orders nothing that day.
    """

    def choose(day: Day, items: list[FoodItem]) -> FoodItem | None:
        source = stdin or sys.stdin
        out = stderr or sys.stderr
        by_number = {item.number: item for item in items}

        out.write(f"\n{describe_day(day)} -- vyberte jídlo:\n")
        for item in items:
            out.write(f"    {item.number}. {item.label}\n")
        while True:
            out.write(f"Číslo jídla ({', '.join(by_number)}), Enter = nic: ")
            out.flush()
            line = source.readline()
            if not line:
                out.write("\n")
                return None
            answer = line.strip().rstrip(".")
            if not answer:
                return None
            if answer in by_number:
                return by_number[answer]
            out.write(f"{answer!r} není v nabídce.\n")

    return choose


def choose_nothing(day: Day, items: list[FoodItem]) -> None:
    """For runs nobody can answer, e.g. from cron: the day is left out."""
    LOG.warning("%s offers %d dishes and nobody can choose: skipped", describe_day(day), len(items))
    return None
