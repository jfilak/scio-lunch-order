"""A stub of the Playwright page that mimics the postbacks of the ASP.NET site.

No browser is involved: :class:`FakePage` models what the site does -- each
postback replaces the page, so a different set of selectors becomes available.
Like in a browser, the old page stays until something waits for the new one:
a ``wait_for_selector`` matching an element of the old page returns at once.
The login states are described by selector sets.  The states of the order
flow serve saved pages from ``tests/data`` and answer selectors from their
markup.  :class:`CanteenPage` goes further and takes any number of orders
and cancellations.
"""

import re
from collections.abc import Callable
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from scio_lunch_order.parser import parse_menu
from scio_lunch_order.selection import WEEKDAYS, czech_date

DATA = Path(__file__).parent / "data"
PASSWORD = "s3cret"

# The 'Objednat' link of dish 3 on pátek 16. října, not ordered in
# order_confirm.html and ordered in order_done.html.
ORDER_LINK_ID = "repeaterDays_ctl03_repeaterFoodType_ctl00_repeaterFood_ctl00_btnFood"
ORDER_LINK = f'a[id="{ORDER_LINK_ID}"]'
# The 'Zrušit objednávku' link of dish 3 on zítra, 23. listopadu, whose
# dialog cancel_confirm.html shows.
CANCEL_LINK_ID = "repeaterDays_ctl00_repeaterFoodType_ctl00_repeaterFood_ctl00_btnFood2"
CANCEL_LINK = f'a[id="{CANCEL_LINK_ID}"]'
CONFIRM_YES = "a#btnDialogYes"


class FakeLocator:
    def __init__(self, present: bool) -> None:
        self._present = present

    def count(self) -> int:
        return 1 if self._present else 0


class FakePage:
    SELECTORS = {
        # The anonymous page shows the public menu too.
        "anonymous": {"a#cmdLoginUser", ".warea"},
        "form": {"input#txtLoginA", "input#txtLoginB", "a#cmdLogin"},
        "menu": {"a#cmdLogoutUser", ".warea"},
    }

    def __init__(
        self,
        state: str = "anonymous",
        pages: dict[str, str] | None = None,
        transitions: dict[tuple[str, str], str] | None = None,
    ) -> None:
        self.state = state
        # state -> the HTML served in that state
        self.pages = dict(pages or {})
        # (state, clicked selector) -> the state after the postback
        self.transitions = dict(transitions or {})
        self.values: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []
        # Replaces the page with the one a click loads, once that is waited for.
        self._loading: Callable[[], None] | None = None

    def _present(self, selector: str) -> bool:
        if self.state in self.pages:
            return bool(_soup(self.pages[self.state]).select(selector))
        return any(part.strip() in self.SELECTORS[self.state] for part in selector.split(","))

    # -- the slice of the Playwright API that LunchSite uses ---------------

    def goto(self, url: str, **_kwargs) -> None:
        self.calls.append(("goto", url))

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self._present(selector))

    def wait_for_selector(self, selector: str, **_kwargs) -> None:
        if self._present(selector):
            return
        self._load()
        if not self._present(selector):
            raise PlaywrightTimeoutError(f"Timeout waiting for {selector}")

    @contextmanager
    def expect_navigation(self, **_kwargs):
        yield
        if not self._load():
            raise PlaywrightTimeoutError("Timeout waiting for navigation")

    def fill(self, selector: str, value: str) -> None:
        assert self._present(selector), f"filling a missing {selector}"
        self.values[selector] = value
        self.calls.append(("fill", selector))

    def click(self, selector: str) -> None:
        assert self._present(selector), f"clicking a missing {selector}"
        self.calls.append(("click", selector))
        self._loading = self._postback(selector)

    def content(self) -> str:
        if self.state in self.pages:
            return self.pages[self.state]
        return '<div class="warea"></div>' if self.state == "menu" else "<html></html>"

    def inner_text(self, _selector: str) -> str:
        return "Nesprávné jméno nebo heslo" if self.state == "form" else ""

    # -- the model of the site ---------------------------------------------

    def _postback(self, selector: str) -> Callable[[], None] | None:
        """What loading the page after a click on ``selector`` does.

        ``None`` for a click that does not post back.
        """
        if (self.state, selector) in self.transitions:
            new_state = self.transitions[(self.state, selector)]
        elif selector == "a#cmdLoginUser":
            new_state = "form"
        elif selector == "a#cmdLogin":
            new_state = "menu" if self.values.get("input#txtLoginB") == PASSWORD else "form"
        else:
            return None
        return lambda: setattr(self, "state", new_state)

    def _load(self) -> bool:
        """Finish loading the page a click asked for; False if there is none."""
        if self._loading is None:
            return False
        self._loading()
        self._loading = None
        return True


@lru_cache(maxsize=16)
def _soup(html: str) -> BeautifulSoup:
    """Parsed once per page: the pages are large and selectors many."""
    return BeautifulSoup(html, "html.parser")


def read_page(name: str) -> str:
    return (DATA / name).read_text(encoding="utf-8")


def remove_element(html: str, element_id: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    soup.find(id=element_id).decompose()
    return str(soup)


def add_info_panel(html: str, text: str) -> str:
    """``html`` with the popup the site shows after an order on top."""
    panel = BeautifulSoup(read_page("order_done.html"), "html.parser").find(id="infoPanel")
    panel.find(class_="popupinfo__label").string = text
    return html.replace('<div class="sticky">', f'{panel}<div class="sticky">', 1)


MENU_PAGE = remove_element(read_page("order_confirm.html"), "dialogPanel")
CONFIRM_PAGE = read_page("order_confirm.html")
DONE_PAGE = read_page("order_done.html")
# 23.-27. listopadu, dish 3 ordered on every day; 24. and 27. offer dish 6 too.
ORDERED_MENU_PAGE = remove_element(read_page("cancel_confirm.html"), "dialogPanel")
CANCEL_CONFIRM_PAGE = read_page("cancel_confirm.html")


def order_page(
    confirm: str = CONFIRM_PAGE,
    done: str = DONE_PAGE,
) -> FakePage:
    """A logged-in menu page on which dish 3 of pátek 16. října can be ordered.

    Clicking its link shows ``confirm``, answering ``Ano`` shows ``done``.
    """
    return FakePage(
        state="menu",
        pages={"menu": MENU_PAGE, "confirm": confirm, "done": done},
        transitions={
            ("menu", ORDER_LINK): "confirm",
            ("confirm", CONFIRM_YES): "done",
        },
    )


def cancel_page(confirm: str = CANCEL_CONFIRM_PAGE, done: str | None = None) -> FakePage:
    """A logged-in menu on which dish 3 of zítra, 23. listopadu can be cancelled.

    Clicking its 'Zrušit objednávku' shows ``confirm``, answering ``Ano``
    shows ``done``: by default the menu with the dish cancelled.
    """
    if done is None:
        soup = BeautifulSoup(ORDERED_MENU_PAGE, "html.parser")
        _mark_cancelled(soup, CANCEL_LINK_ID)
        done = add_info_panel(str(soup), "Vaše objednávka byla zrušena")
    return FakePage(
        state="menu",
        pages={"menu": ORDERED_MENU_PAGE, "confirm": confirm, "done": done},
        transitions={
            ("menu", CANCEL_LINK): "confirm",
            ("confirm", CONFIRM_YES): "done",
        },
    )


def order_link(day: int, food_type: int) -> str:
    """The selector of 'Objednat' of the ``food_type``-th dish of the ``day``-th day."""
    return (
        f'a[id="repeaterDays_ctl{day:02}_repeaterFoodType_ctl{food_type:02}'
        '_repeaterFood_ctl00_btnFood"]'
    )


def cancel_link(day: int, food_type: int) -> str:
    """The selector of 'Zrušit objednávku' of the ``food_type``-th dish of the ``day``-th day."""
    return order_link(day, food_type).replace('btnFood"]', 'btnFood2"]')


def link_id(selector: str) -> str:
    """``a[id="..."]`` -> the id."""
    return re.fullmatch(r'a\[id="(.+)"\]', selector).group(1)


class CanteenPage(FakePage):
    """A logged-in menu that takes orders and cancellations the way the site does.

    'Objednat' shows the dialog about its dish, 'Ano' marks the dish as
    ordered, charges ``PRICE`` and shows the popup -- the popup stays in the
    markup of the next page.  'Zrušit objednávku' does the reverse: its 'Ano'
    removes the link and the green 'Objednáno' mark, and refunds ``PRICE``.
    The links in ``refuse`` get the popup with an error instead of the dialog.
    """

    PRICE = 100

    def __init__(self, html: str = MENU_PAGE, refuse: tuple[str, ...] = ()) -> None:
        super().__init__(state="menu", pages={"menu": html})
        self.refuse = refuse
        self._pending: str | None = None

    def _postback(self, selector: str) -> Callable[[], None] | None:
        if self.state != "menu":  # logged out: the login pages of FakePage
            return super()._postback(selector)
        soup = BeautifulSoup(self.pages["menu"], "html.parser")
        for panel in soup.select("#dialogPanel, #infoPanel"):
            panel.decompose()

        if selector == CONFIRM_YES:
            if self._pending.endswith("2"):
                _mark_cancelled(soup, self._pending)
                _add_credit(soup, self.PRICE)
                panel = _info_panel("Vaše objednávka byla zrušena")
            else:
                link = soup.find(id=self._pending)
                cancel = soup.new_tag("a", id=f"{self._pending}2", href="javascript:void(0)")
                cancel.string = "Zrušit objednávku"
                link.insert_after(cancel)
                _add_credit(soup, -self.PRICE)
                panel = _info_panel("Vaše objednávka byla úspěšně provedena")
            self._pending = None
        elif selector in self.refuse:
            panel = _info_panel("Objednávky na tento den jsou uzavřeny")
        else:
            self._pending = link_id(selector)
            panel = self._dialog(self._pending)

        soup.find(class_="sticky").insert_before(BeautifulSoup(panel, "html.parser"))
        return lambda: self.pages.__setitem__("menu", str(soup))

    def _dialog(self, element_id: str) -> str:
        menu = parse_menu(self.pages["menu"])
        day, item = next(
            (day, item)
            for day in menu.days
            for item in day.items
            for action in (item.order_action, item.cancel_action)
            if action and action.element_id == element_id
        )
        if item.cancel_action and item.cancel_action.element_id == element_id:
            header, question = "Zrušení objednávky", "Opravdu si přejete zrušit objednávku"
        else:
            header, question = "Objednání stravy", "Opravdu si přejete objednat"
        dish = item.label[0].lower() + item.label[1:]
        return (
            '<div id="dialogPanel" class="popupmsgbck zix103">'
            f'<div class="paneldlg__header">{header}</div><span class="paneldlg__msg">'
            f"{question} <br>{dish} dne "
            f"{WEEKDAYS[day.date.weekday()]} {czech_date(day.date)}, jídelna Jídelna?</span>"
            '<a id="btnDialogYes" href="javascript:void(0)">Ano</a>'
            '<a id="btnDialogNo" href="javascript:void(0)">Ne</a></div>'
        )


def _mark_cancelled(soup: BeautifulSoup, cancel_id: str) -> None:
    """Remove the cancel link and the green 'Objednáno' marks of its dish."""
    link = soup.find(id=cancel_id)
    block = link.find_parent(class_="fblock")
    for mark in block.find_all("img", title="Objednáno") if block else ():
        mark.decompose()
    link.decompose()


def _add_credit(soup: BeautifulSoup, amount: int) -> None:
    credit = soup.find(id="lblUserSpec")
    balance = int(re.search(r"(-?\d+) Kč", credit.get_text()).group(1)) + amount
    credit.string = f"Stav účtu:\xa0{balance} Kč"


def _info_panel(text: str) -> str:
    return (
        '<div id="infoPanel" class="popupmsgbck zix103 infobck">'
        f'<div class="popupinfo__label">{text}</div></div>'
    )
