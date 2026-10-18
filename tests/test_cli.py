"""The command line, with the browser replaced by the stub of :mod:`fake_site`."""

import io
import json
import logging
import sys

import pytest
from fake_site import (
    CONFIRM_YES,
    DATA,
    MENU_PAGE,
    ORDER_LINK,
    PASSWORD,
    CanteenPage,
    add_info_panel,
    order_link,
    order_page,
)

from scio_lunch_order import cli
from scio_lunch_order.browser import LunchSite

LOGIN = ["--user", "parent", "--password", "secret", "--pause", "0", "--no-color"]
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


class Terminal(io.StringIO):
    """Answers typed on a terminal; each read is logged among the page calls."""

    def __init__(self, answers: str, calls: list) -> None:
        super().__init__(answers)
        self.calls = calls

    def isatty(self) -> bool:
        return True

    def readline(self, *args) -> str:
        line = super().readline(*args)
        self.calls.append(("answer", line))
        return line


# 15. -> 6, 19. -> nothing, 20. -> a typo, then 3, 23. -> 6
ANSWERS = "6\n\nx\n3\n6\n"


def test_order_all_asks_everything_first_then_orders(use_page, monkeypatch, capsys):
    page = use_page(CanteenPage())
    monkeypatch.setattr(sys, "stdin", Terminal(ANSWERS, page.calls))
    assert cli.main(["order-all", *LOGIN]) == 0

    kinds = [call for call, _selector in page.calls if call in ("answer", "click")]
    assert kinds == ["answer"] * 5 + ["click"] * 12
    out, err = capsys.readouterr()
    assert out.startswith(
        "Celý jídelníček: objednáno: 6, už bylo objednáno: 2, přeskočeno: 1\n"
    )
    assert "Přeskočeno: pondělí 19. října (2026-10-19)\n    nic nevybráno\n" in out
    assert out.endswith("Stav účtu: 1\xa0700\xa0Kč → 1\xa0100\xa0Kč\n")
    assert err.count("vyberte jídlo") == 4


def test_order_all_without_a_terminal_orders_the_single_dish_days(
    use_page, monkeypatch, capsys, caplog
):
    page = use_page(CanteenPage())
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    with caplog.at_level(logging.WARNING):
        assert cli.main(["order-all", *LOGIN]) == 0

    assert clicks(page)[::2] == [order_link(3, 0), order_link(6, 0), order_link(7, 0)]
    out = capsys.readouterr().out
    assert out.startswith("Celý jídelníček: objednáno: 3, už bylo objednáno: 2, přeskočeno: 4\n")
    assert caplog.text.count("nobody can choose") == 4


def test_order_all_logs_in_again_when_logged_out_while_choosing(use_page, monkeypatch):
    page = use_page(CanteenPage())

    class LoggedOutWhileAnswering(Terminal):
        def readline(self, *args) -> str:
            page.state = "anonymous"
            return super().readline(*args)

    monkeypatch.setattr(sys, "stdin", LoggedOutWhileAnswering(ANSWERS, page.calls))
    login = ["--user", "parent", "--password", PASSWORD, "--pause", "0"]
    assert cli.main(["order-all", *login]) == 0
    assert clicks(page)[:3] == ["a#cmdLoginUser", "a#cmdLogin", order_link(2, 1)]
    assert len(clicks(page)) == 2 + 12


def test_order_all_stops_at_a_failure(use_page, monkeypatch, capsys):
    page = use_page(CanteenPage(refuse=(order_link(3, 0),)))
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert cli.main(["order-all", *LOGIN]) == 1

    assert clicks(page) == [order_link(3, 0)]
    out = capsys.readouterr().out
    assert "chyba: 1" in out.splitlines()[0]
    assert "Chyba: pátek 16. října (2026-10-16)" in out
    assert "Objednávky na tento den jsou uzavřeny" in out


def test_order_all_as_json(use_page, monkeypatch, capsys):
    use_page(CanteenPage())
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert cli.main(["order-all", "--json", *LOGIN]) == 0

    data = json.loads(capsys.readouterr().out)
    assert [day["status"] for day in data["days"]].count("ordered") == 3
    assert data["days"][4] == {
        "status": "skipped",
        "day": {"label": "pondělí 19. října", "date": "2026-10-19"},
        "item": None,
        "message": "nic nevybráno",
        "credit_before": None,
        "credit_after": None,
    }
    assert (data["credit_before"], data["credit_after"]) == ("1700", "1400")


def test_order_all_dry_run_still_asks_but_does_not_click(use_page, monkeypatch, capsys):
    page = use_page(CanteenPage())
    monkeypatch.setattr(sys, "stdin", Terminal(ANSWERS, page.calls))
    assert cli.main(["order-all", "--dry-run", *LOGIN]) == 0

    assert clicks(page) == []
    assert "neobjednáno (--dry-run): 6" in capsys.readouterr().out


def test_order_all_from_file_orders_nothing(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    path = DATA / "order_confirm.html"
    assert cli.main(["order-all", "--from-file", str(path), "--no-color"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Celý jídelníček: už bylo objednáno: 2, neobjednáno (--dry-run): 3")
    assert out.endswith("Stav účtu: 1\xa0700\xa0Kč\n")


def test_pause_defaults_to_a_human_pace():
    args = cli._parse_args(["order-all", "-u", "parent"])
    assert cli._browser_options(args).pause_s == 2.0
