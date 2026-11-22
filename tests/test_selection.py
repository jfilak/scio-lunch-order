from datetime import date
from pathlib import Path

import pytest

from scio_lunch_order.models import Day, FoodItem
from scio_lunch_order.parser import parse_menu
from scio_lunch_order.selection import (
    SelectionError,
    czech_date,
    ensure_cancellable,
    ensure_orderable,
    find_item,
    find_ordered_item,
    parse_day_spec,
    parse_item_spec,
)

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="module")
def menu():
    """13.-23. října; dish 3 is ordered on the 13th and the 14th."""
    return parse_menu((DATA / "order_confirm.html").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-10-16", (16, 10, 2026, None)),
        ("16.10.2026", (16, 10, 2026, None)),
        ("16. 10.", (16, 10, None, None)),
        ("16.10", (16, 10, None, None)),
        ("16. října", (16, 10, None, None)),
        ("16. října 2026", (16, 10, 2026, None)),
        ("pátek 16. října", (16, 10, None, 4)),
        ("Pátek, 16.\xa0října", (16, 10, None, 4)),
        ("patek 16. rijna", (16, 10, None, 4)),
        ("zítra, 13. října", (13, 10, None, None)),
        ("29. února", (29, 2, None, None)),
    ],
)
def test_day_formats(text, expected):
    spec = parse_day_spec(text)
    assert (spec.day, spec.month, spec.year, spec.weekday) == expected
    assert spec.text == text


@pytest.mark.parametrize(
    "text",
    ["", "pátek", "blah", "2026-13-01", "31. listopadu", "16. říjen", "pátkem 16. října"],
)
def test_invalid_days_are_rejected(text):
    with pytest.raises(SelectionError):
        parse_day_spec(text)


@pytest.mark.parametrize(("text", "expected"), [("3", "3"), ("6.", "6"), (" 1 ", "1"), ("03", "3")])
def test_item_numbers(text, expected):
    assert parse_item_spec(text) == expected


@pytest.mark.parametrize("text", ["", "x", "3a", "Oběd 3", "-1"])
def test_invalid_item_numbers_are_rejected(text):
    with pytest.raises(SelectionError):
        parse_item_spec(text)


def test_dish_is_found_by_iso_date(menu):
    day, item = find_item(menu, parse_day_spec("2026-10-16"), "3")
    assert day.label == "pátek 16. října"
    assert item.label.startswith("Rybí nugetky z tresky")


def test_dish_is_found_by_date_not_by_label_text(menu):
    # The site writes "zítra, 13. října", the user writes the weekday.
    day, item = find_item(menu, parse_day_spec("úterý 13. října"), "6")
    assert day.label == "zítra, 13. října"
    assert item.number == "6"


def test_weekday_must_match_the_date(menu):
    with pytest.raises(SelectionError, match="2026-10-16 is pátek, not středa"):
        find_item(menu, parse_day_spec("středa 16. října"), "3")


def test_missing_day_lists_the_menu_days(menu):
    with pytest.raises(SelectionError) as error:
        find_item(menu, parse_day_spec("sobota 17. října"), "3")
    assert "2026-10-16, 2026-10-19" in str(error.value)


def test_year_must_match_when_given(menu):
    with pytest.raises(SelectionError):
        find_item(menu, parse_day_spec("16. října 2025"), "3")


def test_missing_dish_lists_the_dishes_of_the_day(menu):
    with pytest.raises(SelectionError, match=r"no dish 6 on pátek 16\. října .*available: 3"):
        find_item(menu, parse_day_spec("2026-10-16"), "6")


def test_a_free_day_can_be_ordered(menu):
    day, item = find_item(menu, parse_day_spec("2026-10-19"), "6")
    ensure_orderable(day, item)


def test_another_ordered_dish_blocks_the_order(menu):
    day, item = find_item(menu, parse_day_spec("2026-10-13"), "6")
    with pytest.raises(SelectionError, match="already has dish 3 ordered"):
        ensure_orderable(day, item)


def test_dish_without_an_order_link_cannot_be_ordered():
    item = FoodItem(number="3", label="Guláš")
    with pytest.raises(SelectionError, match="cannot be ordered"):
        ensure_orderable(Day(label="pátek 16. října", date=date(2026, 10, 16)), item)


def test_the_ordered_dish_of_a_day_is_found_without_a_number(menu):
    day, item = find_ordered_item(menu, parse_day_spec("zítra, 13. října"))
    assert (day.date, item.number) == (date(2026, 10, 13), "3")
    ensure_cancellable(day, item)


def test_a_day_with_nothing_ordered_has_no_dish_to_cancel(menu):
    day, item = find_ordered_item(menu, parse_day_spec("2026-10-16"))
    assert (day.date, item) == (date(2026, 10, 16), None)


def test_the_dish_to_cancel_can_be_given_by_its_number(menu):
    _day, item = find_ordered_item(menu, parse_day_spec("2026-10-13"), "6")
    assert (item.number, item.ordered) == ("6", False)


def test_more_ordered_dishes_need_a_number():
    menu = parse_menu((DATA / "order_confirm.html").read_text(encoding="utf-8"))
    day = next(day for day in menu.days if day.date == date(2026, 10, 13))
    day.items[1].ordered = True  # dish 6 ordered as well, e.g. on the site
    with pytest.raises(SelectionError, match="dishes 3, 6 ordered -- choose one with --item"):
        find_ordered_item(menu, parse_day_spec("2026-10-13"))


def test_dish_without_a_cancel_link_cannot_be_cancelled():
    item = FoodItem(number="3", label="Guláš", ordered=True)
    with pytest.raises(SelectionError, match="cannot be cancelled"):
        ensure_cancellable(Day(label="pátek 16. října", date=date(2026, 10, 16)), item)


def test_czech_date_matches_the_dialog_text():
    assert czech_date(date(2026, 10, 16)) == "16. října 2026"
    assert czech_date(date(2027, 1, 4)) == "4. ledna 2027"
