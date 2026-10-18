"""``order-all``: choosing the dishes, then ordering them one after another.

The menu is ``order_confirm.html``: 13. and 14. října have dish 3 ordered,
16., 21. and 22. offer one dish, the other days dishes 3 and 6.
"""

from datetime import date

import pytest
from fake_site import CONFIRM_YES, MENU_PAGE, CanteenPage, order_link

from scio_lunch_order.browser import LunchSite
from scio_lunch_order.models import Action, FoodItem, OrderResult
from scio_lunch_order.ordering import choose_dishes, order_chosen
from scio_lunch_order.parser import parse_menu
from scio_lunch_order.selection import SelectionError


class ListChooser:
    """Answers with the given dish numbers (``None``: nothing), in turn."""

    def __init__(self, *answers: str | None) -> None:
        self.answers = list(answers)
        self.asked: list[tuple[date, list[str]]] = []

    def __call__(self, day, items):
        self.asked.append((day.date, [item.number for item in items]))
        number = self.answers.pop(0)
        return next((item for item in items if item.number == number), None)


def summary(results):
    return [
        (result.day.date.day, result.status, result.item.number if result.item else None)
        for result in results
    ]


def clicks(page):
    return [selector for call, selector in page.calls if call == "click"]


def test_days_with_one_dish_are_chosen_without_asking():
    chooser = ListChooser("6", None, "3", "6")
    plan = choose_dishes(parse_menu(MENU_PAGE), chooser)

    assert chooser.asked == [
        (date(2026, 10, 15), ["3", "6"]),
        (date(2026, 10, 19), ["3", "6"]),
        (date(2026, 10, 20), ["3", "6"]),
        (date(2026, 10, 23), ["3", "6"]),
    ]
    assert summary(plan) == [
        (13, "already-ordered", "3"),
        (14, "already-ordered", "3"),
        (15, "chosen", "6"),
        (16, "chosen", "3"),
        (19, "skipped", None),
        (20, "chosen", "3"),
        (21, "chosen", "3"),
        (22, "chosen", "3"),
        (23, "chosen", "6"),
    ]


def test_chooser_must_pick_an_offered_dish():
    with pytest.raises(SelectionError, match="not offered"):
        choose_dishes(parse_menu(MENU_PAGE), lambda day, items: FoodItem("9", "Guláš"))


def test_chosen_days_are_ordered_one_after_another():
    page = CanteenPage()
    plan = choose_dishes(parse_menu(page.content()), ListChooser("6", None, "3", "6"))
    results = order_chosen(LunchSite(page=page), page.content(), plan)

    assert clicks(page) == [
        order_link(2, 1), CONFIRM_YES,  # 15. 6
        order_link(3, 0), CONFIRM_YES,  # 16. 3
        order_link(5, 0), CONFIRM_YES,  # 20. 3
        order_link(6, 0), CONFIRM_YES,  # 21. 3
        order_link(7, 0), CONFIRM_YES,  # 22. 3
        order_link(8, 1), CONFIRM_YES,  # 23. 6
    ]  # fmt: skip
    assert [status for _day, status, _number in summary(results)] == [
        "already-ordered",
        "already-ordered",
        "ordered",
        "ordered",
        "skipped",
        "ordered",
        "ordered",
        "ordered",
        "ordered",
    ]
    ordered = [day.date.day for day in parse_menu(page.content()).days if day.ordered]
    assert ordered == [13, 14, 15, 16, 20, 21, 22, 23]
    # Every order is charged against the credit shown by the previous one.
    assert [result.credit_after for result in results if result.credit_after] == [
        1600, 1500, 1400, 1300, 1200, 1100,
    ]  # fmt: skip


def test_dry_run_clicks_nothing():
    page = CanteenPage()
    plan = choose_dishes(parse_menu(page.content()), ListChooser("6", None, "3", "6"))
    results = order_chosen(LunchSite(page=page), page.content(), plan, dry_run=True)

    assert clicks(page) == []
    assert [status for _day, status, _number in summary(results)].count("dry-run") == 6


def test_a_failure_of_the_site_stops_the_run():
    page = CanteenPage(refuse=(order_link(5, 0),))
    plan = choose_dishes(parse_menu(page.content()), ListChooser("6", None, "3", "6"))
    results = order_chosen(LunchSite(page=page), page.content(), plan)

    assert clicks(page)[-1] == order_link(5, 0)
    assert summary(results)[2:] == [
        (15, "ordered", "6"),
        (16, "ordered", "3"),
        (19, "skipped", None),
        (20, "failed", "3"),
        (21, "skipped", "3"),
        (22, "skipped", "3"),
        (23, "skipped", "6"),
    ]
    assert "Objednávky na tento den jsou uzavřeny" in results[5].message
    assert results[6].message == "nezkoušeno kvůli chybě"


def test_a_day_ordered_meanwhile_fails_alone():
    page = CanteenPage()
    plan = choose_dishes(parse_menu(page.content()), ListChooser("6", None, "3", "6"))
    # Somebody orders dish 3 of the 15th on the site after the choice was made.
    friday_3 = order_link(2, 0)[len('a[id="') : -len('"]')]
    LunchSite(page=page).order(Action("Objednat", friday_3), expected_date="15. října 2026")

    results = order_chosen(LunchSite(page=page), page.content(), plan)
    assert summary(results)[2] == (15, "failed", "6")
    assert "already has dish 3 ordered" in results[2].message
    assert summary(results)[3] == (16, "ordered", "3")
