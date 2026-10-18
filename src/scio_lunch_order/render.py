"""Human readable rendering of a parsed :class:`~.models.Menu`."""

from __future__ import annotations

import textwrap
from decimal import Decimal

from .models import Day, Menu, MenuOption, OrderResult, UserInfo

ORDERED_MARK = "[x]"
FREE_MARK = "[ ]"
CLOSED_MARK = "[-]"

_INDENT = "    "
_DETAIL_INDENT = "        "


class _Palette:
    """ANSI colours, or plain text when colouring is off."""

    CODES = {
        "bold": "1",
        "dim": "2",
        "green": "32",
        "yellow": "33",
        "cyan": "36",
    }

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, style: str, text: str) -> str:
        if not self.enabled or not text:
            return text
        return f"\033[{self.CODES[style]}m{text}\033[0m"


def render_menu(menu: Menu, *, color: bool = True, width: int = 78) -> str:
    """Render the whole menu as a block of text."""
    paint = _Palette(color)
    if not menu.days:
        return "Jídelníček je prázdný."

    lines = [_summary(menu, paint), ""]
    for day in menu.days:
        lines.extend(_render_day(day, paint, width))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_user(user: UserInfo, *, color: bool = True) -> str:
    """Render the logged-in user and their account credit as one line."""
    paint = _Palette(color)
    line = f"Strávník: {paint('bold', user.full_name)}"
    if user.credit is not None:
        credit = format_credit(user.credit)
        line += f", stav účtu: {paint('green' if user.credit > 0 else 'yellow', credit)}"
    return line + "\n"


def render_order_result(result: OrderResult, *, color: bool = True, width: int = 78) -> str:
    """Render the outcome of the ``order`` command."""
    paint = _Palette(color)
    headline = {
        OrderResult.ORDERED: paint("green", "Objednáno"),
        OrderResult.ALREADY_ORDERED: paint("green", "Už bylo objednáno"),
        OrderResult.DRY_RUN: paint("yellow", "Neobjednáno (--dry-run)"),
    }[result.status]
    day = result.day
    date = f" ({day.date.isoformat()})" if day.date else ""
    lines = [f"{headline}: {paint('bold', day.label or '?')}{date}"]

    item = result.item
    number = f"{item.number}. " if item.number else ""
    lines.extend(_wrap(f"{number}{item.label}", _INDENT, width, paint))
    if result.message:
        lines.extend(_wrap(result.message, _INDENT, width, paint, "dim"))

    if result.credit_before is not None:
        credit = format_credit(result.credit_before)
        if result.credit_after is not None and result.credit_after != result.credit_before:
            credit += f" → {format_credit(result.credit_after)}"
        lines.append(f"Stav účtu: {credit}")
    return "\n".join(lines) + "\n"


def format_credit(amount: Decimal) -> str:
    """``Decimal("1235.5")`` -> ``1 235,50 Kč`` (Czech number format)."""
    pattern = ",.0f" if amount == amount.to_integral_value() else ",.2f"
    text = format(amount, pattern).replace(",", "\xa0").replace(".", ",")
    return f"{text}\xa0Kč"


def _summary(menu: Menu, paint: _Palette) -> str:
    ordered = len(menu.ordered_items)
    total = len(menu.items)
    head = paint("bold", f"Jídelníček: {len(menu.days)} dnů, {total} položek")
    state = f"{ordered} objednáno"
    return f"{head}, {paint('green' if ordered else 'yellow', state)}"


def _render_day(day: Day, paint: _Palette, width: int) -> list[str]:
    date = day.date.isoformat() if day.date else ""
    title = paint("bold", day.label or "?")
    padding = max(1, width - len(day.label or "?") - len(date))
    lines = [f"{title}{' ' * padding}{paint('dim', date)}", paint("dim", "-" * width)]

    if not day.options:
        lines.append(f"{_INDENT}{paint('dim', 'bez nabídky')}")
    for index, option in enumerate(day.options):
        if index:
            lines.append("")
        lines.extend(_render_option(option, paint, width))
    return lines


def _render_option(option: MenuOption, paint: _Palette, width: int) -> list[str]:
    name = option.name or "?"
    lines = [f"{_INDENT}{paint('cyan', name)}"]
    if option.soup:
        lines.extend(_wrap(f"polévka: {option.soup}", _DETAIL_INDENT, width, paint, "dim"))

    for item in option.items:
        if item.ordered:
            mark = paint("green", ORDERED_MARK)
        elif item.can_order:
            mark = FREE_MARK
        else:
            mark = paint("dim", CLOSED_MARK)

        number = f"{item.number}. " if item.number else ""
        label = f"{number}{item.label}" or "?"
        wrapped = _wrap(label, _DETAIL_INDENT, width, paint)
        first = wrapped[0].lstrip()
        lines.append(f"{_INDENT}{mark} {first}")
        lines.extend(wrapped[1:])
        if item.allergens:
            allergens = "alergeny: " + ", ".join(item.allergens)
            lines.extend(_wrap(allergens, _DETAIL_INDENT + "  ", width, paint, "dim"))
    return lines


def _wrap(
    text: str,
    indent: str,
    width: int,
    paint: _Palette,
    style: str | None = None,
) -> list[str]:
    wrapped = textwrap.wrap(
        text,
        width=max(width, len(indent) + 20),
        initial_indent=indent,
        subsequent_indent=indent + "  ",
    ) or [indent + text]
    if style is None:
        return wrapped
    return [paint(style, line) for line in wrapped]
