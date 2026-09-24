from pathlib import Path

import pytest

from scio_lunch_order.models import Menu
from scio_lunch_order.parser import parse_menu
from scio_lunch_order.render import render_menu

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
