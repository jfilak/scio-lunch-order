"""Turns the ASP.NET markup of the ``warea`` element into :mod:`.models`.

Parsing is done on plain HTML (no browser involved) so it can be unit tested
against saved pages -- see ``tests/data``.
"""

from __future__ import annotations

import copy
import re
from datetime import date

from bs4 import BeautifulSoup, Tag

from .models import Action, Day, FoodItem, Menu, MenuOption

ORDER_LABEL = "objednat"
CANCEL_LABEL = "zrušit"

_DOPOSTBACK_RE = re.compile(r"__doPostBack\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)")
_DATE_RE = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})")
_WHITESPACE_RE = re.compile(r"\s+")


class ParseError(Exception):
    """Raised when the page does not look like the expected menu page."""


def parse_menu(html: str) -> Menu:
    """Parse a full page (or just the ``warea`` fragment) into a :class:`Menu`."""
    soup = BeautifulSoup(html, "html.parser")
    warea = soup.find(class_="warea")
    if warea is None:
        raise ParseError(
            "no element with class 'warea' found -- not a menu page "
            "(not logged in, or the site layout changed)"
        )

    menu = Menu()
    day: Day | None = None
    option: MenuOption | None = None

    for element in _menu_elements(warea):
        classes = element.get("class", [])
        if "fday" in classes:
            day = _parse_day(element)
            option = None
            menu.days.append(day)
        elif "fheader" in classes:
            day = day or _placeholder_day(menu)
            option = _parse_option(element)
            day.options.append(option)
        elif "fblock" in classes:
            day = day or _placeholder_day(menu)
            if option is None:
                option = MenuOption(name="")
                day.options.append(option)
            option.items.append(_parse_food(element))

    return menu


def _menu_elements(warea: Tag) -> list[Tag]:
    """All day / header / block elements of the menu, in document order.

    ``fblock`` never nests, so a recursive search is safe and copes with the
    markup being wrapped in extra containers.
    """
    wanted = ("fday", "fheader", "fblock")
    return warea.find_all(
        lambda tag: any(cls in tag.get("class", []) for cls in wanted)
    )


def _placeholder_day(menu: Menu) -> Day:
    """Fallback for markup that starts with a header instead of a day."""
    day = Day(label="")
    menu.days.append(day)
    return day


def _parse_day(element: Tag) -> Day:
    label = _clean(
        "".join(str(text) for text in element.find_all(string=True, recursive=False))
    )
    if not label:
        label = _clean(element.get_text(""))
    return Day(label=label, date=_parse_date(element))


def _parse_date(element: Tag) -> date | None:
    """The day's date lives in the id of its anchor: ``mnu21.09.2026 0:00:00``."""
    anchor = element.find("a", id=True)
    if anchor is None:
        return None
    match = _DATE_RE.search(anchor["id"])
    if match is None:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_option(element: Tag) -> MenuOption:
    name = _clean(_text_of(element, "ftype"))
    soup_text, soup_allergens = _split_allergens(element.find(class_="fheader--soupl"))
    return MenuOption(
        name=name,
        soup=soup_text or None,
        soup_allergens=soup_allergens,
    )


def _parse_food(element: Tag) -> FoodItem:
    label, allergens = _split_allergens(element.find(class_="food--label"))
    number = _clean(_text_of(element, "fdata__nmb")).rstrip(".") or None
    actions = _parse_actions(element)
    cancel = actions.get("cancel")
    return FoodItem(
        number=number,
        label=label,
        allergens=allergens,
        ordered=cancel is not None or _has_ordered_mark(element),
        order_action=actions.get("order"),
        cancel_action=cancel,
    )


def _parse_actions(element: Tag) -> dict[str, Action]:
    actions: dict[str, Action] = {}
    for anchor in element.find_all("a", href=True):
        label = _clean(anchor.get_text(""))
        lowered = label.lower()
        if lowered.startswith(ORDER_LABEL):
            kind = "order"
        elif lowered.startswith(CANCEL_LABEL):
            kind = "cancel"
        else:
            continue
        element_id = anchor.get("id")
        if not element_id:
            continue
        match = _DOPOSTBACK_RE.search(anchor["href"])
        actions.setdefault(
            kind,
            Action(
                label=label,
                element_id=element_id,
                postback_target=match.group(1) if match else None,
            ),
        )
    return actions


def _has_ordered_mark(element: Tag) -> bool:
    """The green dot image is the site's own 'ordered' indicator."""
    return element.find("img", title="Objednáno") is not None


def _text_of(element: Tag, class_name: str) -> str:
    found = element.find(class_=class_name)
    return found.get_text("") if found else ""


def _split_allergens(element: Tag | None) -> tuple[str, list[str]]:
    """Return the text of ``element`` without the inline allergen spans.

    The spans sit in the middle of the label, e.g. ``kaše 7<span> (7-mléko)
    </span>, kompot``, so they are cut out rather than stripped from the end.
    """
    if element is None:
        return "", []

    clone = copy.copy(element)
    allergens: list[str] = []
    for span in clone.find_all(class_="allergen"):
        allergens.extend(_parse_allergen_text(span.get_text("")))
        span.decompose()
    return _clean(clone.get_text("")), allergens


def _parse_allergen_text(text: str) -> list[str]:
    cleaned = _clean(text).strip("()")
    return [part.strip() for part in cleaned.split(",") if part.strip()]


def _clean(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.replace("\xa0", " ")).strip()
