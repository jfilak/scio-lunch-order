"""The login and order sequences, exercised against a stub of the ASP.NET page.

See :mod:`fake_site` for how the stub models the postbacks of the site.
"""

import pytest
from fake_site import (
    CANCEL_CONFIRM_PAGE,
    CANCEL_LINK,
    CANCEL_LINK_ID,
    CONFIRM_PAGE,
    CONFIRM_YES,
    MENU_PAGE,
    ORDERED_MENU_PAGE,
    ORDER_LINK,
    ORDER_LINK_ID,
    PASSWORD,
    CanteenPage,
    FakePage,
    add_info_panel,
    cancel_link,
    cancel_page,
    link_id,
    order_link,
    order_page,
)

from scio_lunch_order.browser import (
    BrowserOptions,
    CancelError,
    LoginError,
    LunchSite,
    LunchSiteError,
    OrderError,
)
from scio_lunch_order.models import Action
from scio_lunch_order.parser import parse_info_message, parse_menu

ORDER_ACTION = Action(label="Objednat", element_id=ORDER_LINK_ID)
CANCEL_ACTION = Action(label="Zrušit objednávku", element_id=CANCEL_LINK_ID)
MONDAY = "23. listopadu 2026"


def make_site(state: str = "anonymous") -> tuple[LunchSite, FakePage]:
    page = FakePage(state)
    return LunchSite(page=page), page


def test_login_follows_the_manual_procedure():
    site, page = make_site()
    site.open()
    site.login("parent", PASSWORD)

    assert page.calls == [
        ("goto", site.options.url),
        ("click", "a#cmdLoginUser"),
        ("fill", "input#txtLoginA"),
        ("fill", "input#txtLoginB"),
        ("click", "a#cmdLogin"),
    ]
    assert page.values["input#txtLoginA"] == "parent"
    assert site.is_logged_in()
    assert '<div class="warea">' in site.menu_html()


def test_wrong_password_is_reported_with_the_page_message():
    site, _page = make_site()
    with pytest.raises(LoginError) as error:
        site.login("parent", "wrong")
    message = str(error.value)
    assert "wrong user name or password" in message
    assert "Nesprávné jméno nebo heslo" in message


def test_login_is_skipped_when_the_menu_is_already_there():
    site, page = make_site(state="menu")
    site.login("parent", PASSWORD)
    assert page.calls == []


def test_login_is_not_confused_by_the_public_menu():
    site, _page = make_site()
    assert not site.is_logged_in()


def test_menu_html_fails_when_the_menu_is_not_rendered():
    site, _page = make_site(state="form")
    with pytest.raises(LunchSiteError):
        site.menu_html()


def test_page_property_requires_a_started_browser():
    with pytest.raises(LunchSiteError):
        LunchSite().page


def test_order_clicks_the_dish_and_confirms_the_dialog():
    page = order_page()
    html = LunchSite(page=page).order(ORDER_ACTION, expected_date="16. října 2026")

    assert page.calls == [("click", ORDER_LINK), ("click", CONFIRM_YES)]
    assert parse_info_message(html) == "Vaše objednávka byla úspěšně provedena"
    friday = next(day for day in parse_menu(html).days if day.label == "pátek 16. října")
    assert friday.items[0].ordered


def test_order_is_not_confirmed_when_the_dialog_names_another_day():
    page = order_page(
        confirm=CONFIRM_PAGE.replace("dne pátek 16. října 2026", "dne pondělí 19. října 2026")
    )
    with pytest.raises(OrderError) as error:
        LunchSite(page=page).order(ORDER_ACTION, expected_date="16. října 2026")
    assert "not about 16. října 2026" in str(error.value)
    assert "pondělí 19. října 2026" in str(error.value)
    assert page.calls == [("click", ORDER_LINK)]


def test_order_refused_by_the_site_reports_its_message():
    page = order_page(confirm=add_info_panel(MENU_PAGE, "Objednávky jsou uzavřeny"))
    with pytest.raises(OrderError) as error:
        LunchSite(page=page).order(ORDER_ACTION, expected_date="16. října 2026")
    assert "Objednávky jsou uzavřeny" in str(error.value)
    assert page.calls == [("click", ORDER_LINK)]


def test_order_without_a_dialog_fails():
    page = order_page()
    page.transitions[("menu", ORDER_LINK)] = "menu"
    with pytest.raises(OrderError) as error:
        LunchSite(page=page).order(ORDER_ACTION, expected_date="16. října 2026")
    assert "nothing was ordered" in str(error.value)


def test_order_without_an_answer_to_the_confirmation_fails():
    page = order_page()
    page.transitions[("confirm", CONFIRM_YES)] = "confirm"
    with pytest.raises(OrderError) as error:
        LunchSite(page=page).order(ORDER_ACTION, expected_date="16. října 2026")
    assert "may or may not be ordered" in str(error.value)


def test_every_click_waits_like_a_person(monkeypatch):
    pauses = []
    monkeypatch.setattr("scio_lunch_order.browser.time.sleep", pauses.append)
    site = LunchSite(BrowserOptions(pause_s=2.0), page=order_page())
    site.order(ORDER_ACTION, expected_date="16. října 2026")

    assert len(pauses) == 2
    assert all(1.0 <= pause <= 3.0 for pause in pauses)


def test_no_pause_by_default(monkeypatch):
    monkeypatch.setattr("scio_lunch_order.browser.time.sleep", pytest.fail)
    site, _page = make_site()
    site.login("parent", PASSWORD)


def test_next_order_is_not_answered_by_the_popup_of_the_previous_one():
    # After an order the hidden infoPanel stays on the page; the next click
    # must wait for the new page instead of finding the old popup.
    page = CanteenPage()
    site = LunchSite(page=page)
    site.order(ORDER_ACTION, expected_date="16. října 2026")
    assert parse_info_message(page.content()) is not None

    monday_6 = order_link(4, 1)[len('a[id="') : -len('"]')]
    html = site.order(Action("Objednat", monday_6), expected_date="19. října 2026")
    monday = next(day for day in parse_menu(html).days if day.label == "pondělí 19. října")
    assert [item.ordered for item in monday.items] == [False, True]


def test_cancel_clicks_the_cancel_link_and_confirms_the_dialog():
    page = cancel_page()
    html = LunchSite(page=page).cancel(CANCEL_ACTION, expected_date=MONDAY)

    assert page.calls == [("click", CANCEL_LINK), ("click", CONFIRM_YES)]
    assert parse_info_message(html) == "Vaše objednávka byla zrušena"
    monday = parse_menu(html).days[0]
    assert monday.date.day == 23
    assert not monday.ordered


def test_cancel_is_not_confirmed_when_the_dialog_is_not_a_cancellation():
    # An order dialog, whatever it says, must not be answered by 'cancel'.
    order_dialog = CANCEL_CONFIRM_PAGE.replace(
        '<div class="paneldlg__header">Zrušení objednávky</div>',
        '<div class="paneldlg__header">Objednání stravy</div>',
    )
    page = cancel_page(confirm=order_dialog)
    with pytest.raises(CancelError) as error:
        LunchSite(page=page).cancel(CANCEL_ACTION, expected_date=MONDAY)
    assert "not headed 'Zrušení objednávky' but 'Objednání stravy'" in str(error.value)
    assert page.calls == [("click", CANCEL_LINK)]


def test_cancel_is_not_confirmed_when_the_dialog_names_another_day():
    page = cancel_page(
        confirm=CANCEL_CONFIRM_PAGE.replace("dne pondělí 23. listopadu", "dne úterý 24. listopadu")
    )
    with pytest.raises(CancelError) as error:
        LunchSite(page=page).cancel(CANCEL_ACTION, expected_date=MONDAY)
    assert "not about 23. listopadu 2026, nothing was cancelled" in str(error.value)
    assert page.calls == [("click", CANCEL_LINK)]


def test_cancel_refused_by_the_site_reports_its_message():
    page = cancel_page(confirm=add_info_panel(ORDERED_MENU_PAGE, "Objednávku nelze zrušit"))
    with pytest.raises(CancelError, match="refused the cancellation: Objednávku nelze zrušit"):
        LunchSite(page=page).cancel(CANCEL_ACTION, expected_date=MONDAY)
    assert page.calls == [("click", CANCEL_LINK)]


def test_cancel_without_an_answer_to_the_confirmation_fails():
    page = cancel_page()
    page.transitions[("confirm", CONFIRM_YES)] = "confirm"
    with pytest.raises(CancelError, match="may or may not be cancelled"):
        LunchSite(page=page).cancel(CANCEL_ACTION, expected_date=MONDAY)


def test_next_cancellation_is_not_answered_by_the_popup_of_the_previous_one():
    page = CanteenPage(ORDERED_MENU_PAGE)
    site = LunchSite(page=page)
    site.cancel(CANCEL_ACTION, expected_date=MONDAY)
    assert parse_info_message(page.content()) == "Vaše objednávka byla zrušena"

    tuesday_3 = Action("Zrušit objednávku", link_id(cancel_link(1, 0)))
    html = site.cancel(tuesday_3, expected_date="24. listopadu 2026")
    assert [day.ordered for day in parse_menu(html).days] == [False, False, True, True, True]
