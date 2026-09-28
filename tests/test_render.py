from decimal import Decimal
from pathlib import Path

import pytest

from scio_lunch_order.models import Menu, UserInfo
from scio_lunch_order.parser import parse_menu
from scio_lunch_order.render import format_credit, render_menu, render_user

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
