"""A stub of the Playwright page that mimics the postbacks of the ASP.NET site.

No browser is involved: :class:`FakePage` models what the site does -- each
postback replaces the page, so a different set of selectors becomes available.
The login states are described by selector sets.  The states of the order
flow serve saved pages from ``tests/data`` and answer selectors from their
markup.
"""

from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

DATA = Path(__file__).parent / "data"
PASSWORD = "s3cret"

# The 'Objednat' link of dish 3 on pátek 16. října, not ordered in
# order_confirm.html and ordered in order_done.html.
ORDER_LINK_ID = "repeaterDays_ctl03_repeaterFoodType_ctl00_repeaterFood_ctl00_btnFood"
ORDER_LINK = f'a[id="{ORDER_LINK_ID}"]'
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

    def _present(self, selector: str) -> bool:
        if self.state in self.pages:
            return bool(BeautifulSoup(self.pages[self.state], "html.parser").select(selector))
        return any(part.strip() in self.SELECTORS[self.state] for part in selector.split(","))

    # -- the slice of the Playwright API that LunchSite uses ---------------

    def goto(self, url: str, **_kwargs) -> None:
        self.calls.append(("goto", url))

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self._present(selector))

    def wait_for_selector(self, selector: str, **_kwargs) -> None:
        if not self._present(selector):
            raise PlaywrightTimeoutError(f"Timeout waiting for {selector}")

    def wait_for_load_state(self, *_args, **_kwargs) -> None:
        pass

    def fill(self, selector: str, value: str) -> None:
        assert self._present(selector), f"filling a missing {selector}"
        self.values[selector] = value
        self.calls.append(("fill", selector))

    def click(self, selector: str) -> None:
        assert self._present(selector), f"clicking a missing {selector}"
        self.calls.append(("click", selector))
        if (self.state, selector) in self.transitions:
            self.state = self.transitions[(self.state, selector)]
        elif selector == "a#cmdLoginUser":
            self.state = "form"
        elif selector == "a#cmdLogin" and self.values.get("input#txtLoginB") == PASSWORD:
            self.state = "menu"

    def content(self) -> str:
        if self.state in self.pages:
            return self.pages[self.state]
        return '<div class="warea"></div>' if self.state == "menu" else "<html></html>"

    def inner_text(self, _selector: str) -> str:
        return "Nesprávné jméno nebo heslo" if self.state == "form" else ""


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
