"""Playwright driver for the canteen site.

The site is a classic ASP.NET WebForms application: every button is an
``<a href="javascript:__doPostBack(...)">`` that submits the form and replaces
the page.  Therefore every step clicks a *selector* (never a stale element
handle) and then waits for a selector that can only exist on the next page.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from types import TracebackType

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Playwright, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

DEFAULT_URL = "https://skola.czszlin.cz:4434/iorders/"

LOG = logging.getLogger(__name__)

LAUNCH_HINT = (
    "run 'playwright install chromium'; on Linux the browser also needs system "
    "libraries (nss, nspr, atk, at-spi2-atk, libdrm, mesa-libgbm, alsa-lib, libX*)"
)

_ERROR_HINT_RE = re.compile(r"chyb|nespr[áa]vn|neplatn|špatn|heslo", re.IGNORECASE)


class LunchSiteError(Exception):
    """Something went wrong while driving the site."""


class LoginError(LunchSiteError):
    """The login sequence did not end on the menu page."""


@dataclass
class BrowserOptions:
    url: str = DEFAULT_URL
    headless: bool = True
    timeout_ms: int = 30_000
    slow_mo_ms: int = 0
    ignore_https_errors: bool = False


class LunchSite:
    """A browser session on the canteen site, usable as a context manager."""

    LOGIN_TRIGGER = "a#cmdLoginUser"
    USERNAME_INPUT = "input#txtLoginA"
    PASSWORD_INPUT = "input#txtLoginB"
    LOGIN_SUBMIT = "a#cmdLogin"
    MENU = ".warea"

    def __init__(self, options: BrowserOptions | None = None, page: Page | None = None) -> None:
        """``page`` lets a caller (or a test) drive an already open page."""
        self.options = options or BrowserOptions()
        self._playwright: Playwright | None = None
        self._browser = None
        self._context = None
        self._page: Page | None = page

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> LunchSite:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def start(self) -> None:
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(
                headless=self.options.headless,
                slow_mo=self.options.slow_mo_ms,
            )
            self._context = self._browser.new_context(
                ignore_https_errors=self.options.ignore_https_errors,
            )
            self._context.set_default_timeout(self.options.timeout_ms)
            self._page = self._context.new_page()
        except PlaywrightError as exc:
            # Do not leave the node driver behind when the browser is unusable.
            self.close()
            LOG.debug("chromium launch failed", exc_info=True)
            detail = str(exc).strip().splitlines()[0]
            raise LunchSiteError(f"cannot start Chromium: {detail}\nhint: {LAUNCH_HINT}") from exc
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        for resource in (self._context, self._browser, self._playwright):
            if resource is None:
                continue
            closer = getattr(resource, "close", None) or getattr(resource, "stop", None)
            if closer is None:
                continue
            try:
                closer()
            except Exception:  # noqa: BLE001 - never mask the original failure
                LOG.debug("failed to close %r", resource, exc_info=True)
        self._playwright = self._browser = self._context = self._page = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise LunchSiteError("browser is not started -- use 'with LunchSite(...)'")
        return self._page

    # -- navigation --------------------------------------------------------

    def open(self) -> None:
        LOG.info("opening %s", self.options.url)
        self.page.goto(self.options.url, wait_until="domcontentloaded")

    def login(self, username: str, password: str) -> None:
        """Run the manual login sequence described in the README."""
        if self.is_logged_in():
            LOG.info("already logged in")
            return

        LOG.info("opening the login form")
        self._click(self.LOGIN_TRIGGER, wait_for=self.USERNAME_INPUT)

        LOG.info("submitting credentials for %s", username)
        self.page.fill(self.USERNAME_INPUT, username)
        self.page.fill(self.PASSWORD_INPUT, password)
        try:
            self._click(self.LOGIN_SUBMIT, wait_for=self.MENU)
        except PlaywrightTimeoutError as exc:
            raise LoginError(self._login_failure_hint()) from exc
        LOG.info("logged in")

    def is_logged_in(self) -> bool:
        return self.page.locator(self.LOGIN_TRIGGER).count() == 0

    def menu_html(self) -> str:
        """The current page HTML, waiting for the menu to be rendered."""
        try:
            self.page.wait_for_selector(self.MENU, state="attached")
        except PlaywrightTimeoutError as exc:
            raise LunchSiteError("the menu (.warea) is not present on the page") from exc
        return self.page.content()

    def screenshot(self, path: str) -> None:
        self.page.screenshot(path=path, full_page=True)

    # -- internals ---------------------------------------------------------

    def _click(self, selector: str, wait_for: str) -> None:
        """Click a postback link and wait for the re-rendered page."""
        self.page.wait_for_selector(selector, state="visible")
        self.page.click(selector)
        self.page.wait_for_selector(wait_for, state="visible")

    def _login_failure_hint(self) -> str:
        if self.page.locator(self.USERNAME_INPUT).count() == 0:
            return "the menu did not appear after login"
        message = "the login form is still displayed -- wrong user name or password?"
        detail = self._page_error_text()
        return f"{message} ({detail})" if detail else message

    def _page_error_text(self) -> str | None:
        try:
            body = self.page.inner_text("body")
        except PlaywrightTimeoutError:
            return None
        for line in (line.strip() for line in body.splitlines()):
            if line and _ERROR_HINT_RE.search(line):
                return line[:160]
        return None


def fetch_menu_html(
    username: str,
    password: str,
    options: BrowserOptions | None = None,
) -> str:
    """Log in and return the HTML of the menu page."""
    with LunchSite(options) as site:
        site.open()
        site.login(username, password)
        return site.menu_html()
