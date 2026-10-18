from decimal import Decimal
from pathlib import Path

import pytest

from scio_lunch_order.models import Menu, OrderResult, UserInfo
from scio_lunch_order.parser import parse_menu
from scio_lunch_order.render import (
    format_credit,
    render_menu,
    render_order_result,
    render_user,
)

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="module")
def ordered():
    return parse_menu((DATA / "menu_ordered.html").read_text(encoding="utf-8"))


def test_every_day_and_dish_is_shown(ordered):
    text = render_menu(ordered, color=False)
    for day in ordered.days:
        assert day.label in text
        assert day.date.isoformat() in text
    assert "Játrová omáčka(1), dušená rýže" in text
    assert "polévka: Polévka čočková" in text
    assert "alergeny: 1-lepek, 3-vejce" in text


def test_ordered_items_are_marked(ordered):
    text = render_menu(ordered, color=False)
    assert text.count("[x]") == 5
    assert text.count("[ ]") == 3
    assert "5 objednáno" in text


def test_colour_can_be_switched_off(ordered):
    assert "\033[" not in render_menu(ordered, color=False)
    assert "\033[" in render_menu(ordered, color=True)


def test_long_labels_are_wrapped(ordered):
    wide = render_menu(ordered, color=False, width=100)
    narrow = render_menu(ordered, color=False, width=60)
    for line in narrow.splitlines():
        assert len(line) <= 62, line
    assert len(narrow.splitlines()) > len(wide.splitlines())


def test_empty_menu():
    assert render_menu(Menu(), color=False) == "Jídelníček je prázdný."


def test_user_line():
    user = UserInfo(full_name="Hynek Filák", credit=Decimal("135"))
    assert render_user(user, color=False) == "Strávník: Hynek Filák, stav účtu: 135\xa0Kč\n"


def test_user_line_without_credit():
    assert render_user(UserInfo(full_name="Hynek Filák"), color=False) == (
        "Strávník: Hynek Filák\n"
    )


def test_credit_format():
    assert format_credit(Decimal("-42")) == "-42\xa0Kč"
    assert format_credit(Decimal("1235.5")) == "1\xa0235,50\xa0Kč"


def test_order_result(ordered):
    day = ordered.days[2]
    result = OrderResult(
        OrderResult.ORDERED,
        day,
        day.items[1],
        message="Vaše objednávka byla úspěšně provedena",
        credit_before=Decimal("1700"),
        credit_after=Decimal("1600"),
    )
    assert render_order_result(result, color=False) == (
        "Objednáno: středa 23. září (2026-09-23)\n"
        "    6. Játrová omáčka(1), dušená rýže\n"
        "    Vaše objednávka byla úspěšně provedena\n"
        "Stav účtu: 1\xa0700\xa0Kč → 1\xa0600\xa0Kč\n"
    )


def test_order_result_without_a_change(ordered):
    day = ordered.days[0]
    result = OrderResult(
        OrderResult.ALREADY_ORDERED, day, day.items[0], credit_before=Decimal("135")
    )
    text = render_order_result(result, color=False)
    assert text.startswith("Už bylo objednáno: zítra, 21. září (2026-09-21)\n")
    assert text.endswith("Stav účtu: 135\xa0Kč\n")

    dry_run = OrderResult(OrderResult.DRY_RUN, day, day.items[0])
    assert render_order_result(dry_run, color=False).startswith("Neobjednáno (--dry-run): ")
