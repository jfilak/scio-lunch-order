"""Data model of the canteen menu.

The site renders one ``<div class="warea">`` holding a flat sequence of days,
food-type headers and food blocks.  These classes give that sequence a shape:

    Menu -> Day -> MenuOption ("Oběd 3" + soup) -> FoodItem
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class Action:
    """A clickable ASP.NET link, e.g. ``Objednat`` or ``Zrušit objednávku``.

    ``element_id`` is what Playwright clicks; ``postback_target`` is the
    ``__doPostBack`` argument, kept for debugging and for a possible
    request-level implementation later on.
    """

    label: str
    element_id: str
    postback_target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "element_id": self.element_id,
            "postback_target": self.postback_target,
        }


@dataclass
class FoodItem:
    """A single dish inside a ``<div class="fblock">``."""

    number: str | None
    label: str
    allergens: list[str] = field(default_factory=list)
    ordered: bool = False
    order_action: Action | None = None
    cancel_action: Action | None = None

    @property
    def can_order(self) -> bool:
        return self.order_action is not None

    @property
    def can_cancel(self) -> bool:
        return self.cancel_action is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "label": self.label,
            "allergens": list(self.allergens),
            "ordered": self.ordered,
            "order_action": self.order_action.to_dict() if self.order_action else None,
            "cancel_action": self.cancel_action.to_dict() if self.cancel_action else None,
        }


@dataclass
class MenuOption:
    """One food type of a day -- the ``fheader`` and the ``fblock``s after it."""

    name: str
    soup: str | None = None
    soup_allergens: list[str] = field(default_factory=list)
    items: list[FoodItem] = field(default_factory=list)

    @property
    def ordered(self) -> bool:
        return any(item.ordered for item in self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "soup": self.soup,
            "soup_allergens": list(self.soup_allergens),
            "items": [item.to_dict() for item in self.items],
        }


@dataclass
class Day:
    """A single day of the menu."""

    label: str
    date: date | None = None
    options: list[MenuOption] = field(default_factory=list)

    @property
    def items(self) -> list[FoodItem]:
        return [item for option in self.options for item in option.items]

    @property
    def ordered_items(self) -> list[FoodItem]:
        return [item for item in self.items if item.ordered]

    @property
    def ordered(self) -> bool:
        return bool(self.ordered_items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "date": self.date.isoformat() if self.date else None,
            "ordered": self.ordered,
            "options": [option.to_dict() for option in self.options],
        }


@dataclass
class Menu:
    """The whole ``warea`` -- everything the site shows for the current week."""

    days: list[Day] = field(default_factory=list)

    @property
    def items(self) -> list[FoodItem]:
        return [item for day in self.days for item in day.items]

    @property
    def ordered_items(self) -> list[FoodItem]:
        return [item for item in self.items if item.ordered]

    def to_dict(self) -> dict[str, Any]:
        return {
            "days": [day.to_dict() for day in self.days],
            "summary": {
                "days": len(self.days),
                "items": len(self.items),
                "ordered": len(self.ordered_items),
            },
        }


@dataclass(frozen=True)
class UserInfo:
    """The logged-in user as shown in the page header (``usrblock``)."""

    full_name: str
    credit: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "credit": str(self.credit) if self.credit is not None else None,
        }
