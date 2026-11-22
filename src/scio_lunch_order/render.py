"""Human readable rendering of a parsed :class:`~.models.Menu`, of orders and cancellations."""

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
        "red": "31",
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


_Labels = dict[str, tuple[str, str]]

# status -> (style, label), in the order of the summary of the '-all' commands.
_ORDER_LABELS: _Labels = {
    OrderResult.ORDERED: ("green", "Objednáno"),
    OrderResult.ALREADY_ORDERED: ("green", "Už bylo objednáno"),
    OrderResult.DRY_RUN: ("yellow", "Neobjednáno (--dry-run)"),
    OrderResult.SKIPPED: ("yellow", "Přeskočeno"),
    OrderResult.FAILED: ("red", "Chyba"),
}
_CANCEL_LABELS: _Labels = {
    OrderResult.CANCELLED: ("green", "Zrušeno"),
    OrderResult.NOT_ORDERED: ("dim", "Nebylo objednáno"),
    OrderResult.DRY_RUN: ("yellow", "Nezrušeno (--dry-run)"),
    OrderResult.SKIPPED: ("yellow", "Přeskočeno"),
    OrderResult.FAILED: ("red", "Chyba"),
}


def render_order_result(result: OrderResult, *, color: bool = True, width: int = 78) -> str:
    """Render the outcome of the ``order`` command."""
    return _render_single(result, _ORDER_LABELS, color, width)


def render_cancel_result(result: OrderResult, *, color: bool = True, width: int = 78) -> str:
    """Render the outcome of the ``cancel`` command."""
    return _render_single(result, _CANCEL_LABELS, color, width)


def render_order_results(
    results: list[OrderResult],
    *,
    credit_before: Decimal | None = None,
    credit_after: Decimal | None = None,
    color: bool = True,
    width: int = 78,
) -> str:
    """Render the outcome of the ``order-all`` command, day by day."""
    return _render_many(
        results, _ORDER_LABELS, OrderResult.ORDERED, credit_before, credit_after, color, width
    )


def render_cancel_results(
    results: list[OrderResult],
    *,
    credit_before: Decimal | None = None,
    credit_after: Decimal | None = None,
    color: bool = True,
    width: int = 78,
) -> str:
    """Render the outcome of the ``cancel-all`` command, day by day."""
    return _render_many(
        results, _CANCEL_LABELS, OrderResult.CANCELLED, credit_before, credit_after, color, width
    )


def _render_single(result: OrderResult, labels: _Labels, color: bool, width: int) -> str:
    paint = _Palette(color)
    lines = _render_result(result, labels, paint, width, show_message=True)
    lines.extend(_credit(result.credit_before, result.credit_after))
    return "\n".join(lines) + "\n"


def _render_many(
    results: list[OrderResult],
    labels: _Labels,
    done: str,
    credit_before: Decimal | None,
    credit_after: Decimal | None,
    color: bool,
    width: int,
) -> str:
    paint = _Palette(color)
    if not results:
        return "Jídelníček je prázdný.\n"

    counts = [
        f"{label.lower()}: {count}"
        for status, (_style, label) in labels.items()
        if (count := sum(result.status == status for result in results))
    ]
    lines = [paint("bold", "Celý jídelníček: ") + ", ".join(counts), ""]
    for result in results:
        # The site's 'objednávka byla úspěšně provedena' would repeat on every day.
        show_message = result.status != done
        lines.extend(_render_result(result, labels, paint, width, show_message=show_message))
        lines.append("")
    lines.extend(_credit(credit_before, credit_after))
    return "\n".join(lines).rstrip() + "\n"


def _render_result(
    result: OrderResult, labels: _Labels, paint: _Palette, width: int, *, show_message: bool
) -> list[str]:
    style, label = labels[result.status]
    day = result.day
    date = f" ({day.date.isoformat()})" if day.date else ""
    lines = [f"{paint(style, label)}: {paint('bold', day.label or '?')}{date}"]

    item = result.item
    if item is not None:
        number = f"{item.number}. " if item.number else ""
        lines.extend(_wrap(f"{number}{item.label}", _INDENT, width, paint))
    if result.message and show_message:
        lines.extend(_wrap(result.message, _INDENT, width, paint, "dim"))
    return lines


def _credit(before: Decimal | None, after: Decimal | None) -> list[str]:
    if before is None:
        return []
    credit = format_credit(before)
    if after is not None and after != before:
        credit += f" → {format_credit(after)}"
    return [f"Stav účtu: {credit}"]


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
