"""The command line, with the browser replaced by the stub of :mod:`fake_site`."""

import json

import pytest
from fake_site import CONFIRM_YES, DATA, MENU_PAGE, ORDER_LINK, add_info_panel, order_page

from scio_lunch_order import cli
from scio_lunch_order.browser import LunchSite

LOGIN = ["--user", "parent", "--password", "secret", "--no-color"]
FRIDAY_3 = ["--day", "pátek 16. října", "--item", "3"]


@pytest.fixture
def use_page(monkeypatch):
    """Make the CLI drive the given FakePage instead of starting Chromium."""

    class StubSite(LunchSite):
        def start(self) -> None:
            pass

    def install(page):
        monkeypatch.setattr(cli, "LunchSite", lambda options: StubSite(options, page=page))
        return page

    return install


def clicks(page):
    return [selector for call, selector in page.calls if call == "click"]


def test_order_places_and_verifies_the_order(use_page, capsys):
    page = use_page(order_page())
    assert cli.main(["order", *FRIDAY_3, *LOGIN]) == 0

    assert clicks(page) == [ORDER_LINK, CONFIRM_YES]
    out = capsys.readouterr().out
    assert out.startswith("Objednáno: pátek 16. října (2026-10-16)\n")
    assert "Vaše objednávka byla úspěšně provedena" in out
    assert "Stav účtu: 1\xa0700\xa0Kč → 1\xa0500\xa0Kč" in out


def test_order_as_json(use_page, capsys):
    use_page(order_page())
    assert cli.main(["--json", "order", *FRIDAY_3, *LOGIN]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "ordered"
    assert data["day"] == {"label": "pátek 16. října", "date": "2026-10-16"}
    assert data["item"]["ordered"] is True
    assert (data["credit_before"], data["credit_after"]) == ("1700", "1500")


def test_already_ordered_dish_is_not_clicked_again(use_page, capsys):
    page = use_page(order_page())
    assert cli.main(["order", "--day", "2026-10-14", "--item", "3", *LOGIN]) == 0

    assert clicks(page) == []
    assert capsys.readouterr().out.startswith("Už bylo objednáno: středa 14. října")


def test_dry_run_does_not_click(use_page, capsys):
    page = use_page(order_page())
    assert cli.main(["order", *FRIDAY_3, "--dry-run", *LOGIN]) == 0

    assert clicks(page) == []
    assert capsys.readouterr().out.startswith("Neobjednáno (--dry-run): pátek 16. října")


def test_order_is_refused_when_another_dish_of_the_day_is_ordered(use_page, capsys):
    page = use_page(order_page())
    assert cli.main(["order", "--day", "2026-10-13", "--item", "6", *LOGIN]) == 1

    assert clicks(page) == []
    assert "already has dish 3 ordered" in capsys.readouterr().err


def test_success_popup_without_an_ordered_dish_is_an_error(use_page, capsys):
    done = add_info_panel(MENU_PAGE, "Vaše objednávka byla úspěšně provedena")
    use_page(order_page(done=done))
    assert cli.main(["order", *FRIDAY_3, *LOGIN]) == 1
    assert "not marked as ordered" in capsys.readouterr().err


def test_order_from_file_orders_nothing(capsys):
    path = DATA / "order_confirm.html"
    assert cli.main(["order", "--from-file", str(path), *FRIDAY_3, "--no-color"]) == 0
    assert capsys.readouterr().out.startswith("Neobjednáno (--dry-run): ")


def test_unknown_day_is_an_error(capsys):
    path = DATA / "order_confirm.html"
    argv = ["order", "--from-file", str(path), "--day", "2026-10-17", "--item", "3"]
    assert cli.main(argv) == 1
    assert "'2026-10-17' is not on the menu" in capsys.readouterr().err


def test_menu_is_still_the_default_command(capsys):
    assert cli.main(["--from-file", str(DATA / "menu_ordered.html"), "--no-color"]) == 0
    assert "Jídelníček: 5 dnů" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["--headed", "-u", "parent", "order", *FRIDAY_3],
        ["order", *FRIDAY_3, "--headed", "-u", "parent"],
    ],
)
def test_common_options_work_before_and_after_the_command(monkeypatch, argv):
    monkeypatch.setenv(cli.ENV_USER, "from-env")
    args = cli._parse_args(argv)
    assert args.headed is True
    assert args.user == "parent"
    assert args.timeout == 30.0


def test_order_needs_day_and_item():
    with pytest.raises(SystemExit) as error:
        cli._parse_args(["order", "--day", "2026-10-16", "-u", "parent"])
    assert error.value.code == 2
