"""The login sequence, exercised against a stub of the ASP.NET page.

No browser is involved: :class:`FakePage` models what the site does -- each
postback replaces the page, so a different set of selectors becomes available.
"""

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from scio_lunch_order.browser import LoginError, LunchSite, LunchSiteError

PASSWORD = "s3cret"


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

    def __init__(self, state: str = "anonymous") -> None:
        self.state = state
        self.values: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []

    def _present(self, selector: str) -> bool:
        return any(part.strip() in self.SELECTORS[self.state] for part in selector.split(","))

    # -- the slice of the Playwright API that LunchSite uses ---------------

    def goto(self, url: str, **_kwargs) -> None:
        self.calls.append(("goto", url))

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self._present(selector))

    def wait_for_selector(self, selector: str, **_kwargs) -> None:
        if not self._present(selector):
            raise PlaywrightTimeoutError(f"Timeout waiting for {selector}")

    def fill(self, selector: str, value: str) -> None:
        assert self._present(selector), f"filling a missing {selector}"
        self.values[selector] = value
        self.calls.append(("fill", selector))

    def click(self, selector: str) -> None:
        assert self._present(selector), f"clicking a missing {selector}"
        self.calls.append(("click", selector))
        if selector == "a#cmdLoginUser":
            self.state = "form"
        elif selector == "a#cmdLogin" and self.values.get("input#txtLoginB") == PASSWORD:
            self.state = "menu"

    def content(self) -> str:
        return '<div class="warea"></div>' if self.state == "menu" else "<html></html>"

    def inner_text(self, _selector: str) -> str:
        return "Nesprávné jméno nebo heslo" if self.state == "form" else ""


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
