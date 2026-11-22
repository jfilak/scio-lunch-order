"""Playwright driver for the canteen site.

The site is a classic ASP.NET WebForms application: every button is an
``<a href="javascript:__doPostBack(...)">`` that submits the form and replaces
the page.  Therefore every step clicks a *selector* (never a stale element
handle) and then waits for a selector that can only exist on the next page.

Every click is preceded by a randomised pause (:attr:`BrowserOptions.pause_s`)
so that the site is used at the pace of a person, not of a script.
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from types import TracebackType

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Playwright, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .models import Action
from .parser import parse_confirm_header, parse_confirm_message, parse_info_message

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


class OrderError(LunchSiteError):
    """The site did not take the order the way the README describes."""


class CancelError(LunchSiteError):
    """The site did not cancel the order the way the README describes."""


@dataclass
class BrowserOptions:
    url: str = DEFAULT_URL
    headless: bool = True
    timeout_ms: int = 30_000
    slow_mo_ms: int = 0
    ignore_https_errors: bool = False
    # Average pause before every click; each pause is 0.5-1.5 times as long.
    pause_s: float = 0.0


class LunchSite:
    """A browser session on the canteen site, usable as a context manager."""

    LOGIN_TRIGGER = "a#cmdLoginUser"
    USERNAME_INPUT = "input#txtLoginA"
    PASSWORD_INPUT = "input#txtLoginB"
    LOGIN_SUBMIT = "a#cmdLogin"
    # Only rendered for a logged-in user.  Do not use MENU as the login marker:
    # the anonymous page shows the public menu in a ``.warea`` element as well.
    LOGOUT_LINK = "a#cmdLogoutUser"
    MENU = ".warea"
    CONFIRM_YES = "a#btnDialogYes"
    # The header of the dialog after 'Zrušit objednávku'.
    CANCEL_HEADER = "Zrušení objednávky"
    # The popup after an order or a cancellation; hidden by a script, so wait
    # for it 'attached'.
    INFO_PANEL = "#infoPanel"

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
            self._click(self.LOGIN_SUBMIT, wait_for=self.LOGOUT_LINK)
        except PlaywrightTimeoutError as exc:
            raise LoginError(self._login_failure_hint()) from exc
        LOG.info("logged in")

    def is_logged_in(self) -> bool:
        # Wait until the page decides: either the login link or the logout link.
        try:
            self.page.wait_for_selector(
                f"{self.LOGIN_TRIGGER}, {self.LOGOUT_LINK}", state="attached"
            )
        except PlaywrightTimeoutError as exc:
            raise LunchSiteError("neither the login nor the logout link appeared") from exc
        return self.page.locator(self.LOGOUT_LINK).count() > 0

    def menu_html(self) -> str:
        """The current page HTML, waiting for the menu to be rendered."""
        try:
            self.page.wait_for_selector(self.MENU, state="attached")
        except PlaywrightTimeoutError as exc:
            raise LunchSiteError("the menu (.warea) is not present on the page") from exc
        return self.page.content()

    def screenshot(self, path: str) -> None:
        self.page.screenshot(path=path, full_page=True)

    def order(self, action: Action, expected_date: str) -> str:
        """Click an ``Objednat`` link and answer ``Ano`` in the dialog.

        The dialog repeats the dish and its date (``… dne pátek 16. října
        2026 …``).  Unless the question contains ``expected_date`` it is left
        unanswered, so nothing is ordered.  Returns the HTML of the page shown
        after the order: the menu with the ``infoPanel`` popup.
        """
        return self._confirmed_postback(
            action, expected_date, error=OrderError, what="order", done="ordered"
        )

    def cancel(self, action: Action, expected_date: str) -> str:
        """Click a ``Zrušit objednávku`` link and answer ``Ano`` in the dialog.

        Like :meth:`order`, but the dialog must also be headed ``Zrušení
        objednávky``.  Returns the HTML of the page shown after the
        cancellation: the menu with the ``infoPanel`` popup.
        """
        return self._confirmed_postback(
            action,
            expected_date,
            error=CancelError,
            what="cancellation",
            done="cancelled",
            header=self.CANCEL_HEADER,
        )

    # -- internals ---------------------------------------------------------

    def _confirmed_postback(
        self,
        action: Action,
        expected_date: str,
        *,
        error: type[LunchSiteError],
        what: str,
        done: str,
        header: str | None = None,
    ) -> str:
        """Click ``action``, check the dialog it opens and answer ``Ano``.

        ``what`` and ``done`` word the errors: ``order`` / ``ordered``.  The
        dialog is answered only if its question names ``expected_date`` and,
        when ``header`` is given, its header is ``header``.
        """
        LOG.info("clicking %s (%s)", action.label, action.element_id)
        try:
            html = self._postback(
                f'a[id="{action.element_id}"]',
                wait_for=f"{self.CONFIRM_YES}, {self.INFO_PANEL}",
            )
        except PlaywrightTimeoutError as exc:
            raise error(f"no confirmation dialog appeared, nothing was {done}") from exc

        question = parse_confirm_message(html)
        if question is None:
            reason = parse_info_message(html) or "no confirmation dialog"
            raise error(f"the site refused the {what}: {reason}")
        LOG.info("the site asks: %s", question)
        if header is not None:
            found = parse_confirm_header(html)
            if found is None or found.casefold() != header.casefold():
                raise error(
                    f"the confirmation dialog is not headed {header!r} but {found!r}, "
                    f"nothing was {done}: {question}"
                )
        if expected_date not in question:
            raise error(
                f"the confirmation dialog is not about {expected_date}, "
                f"nothing was {done}: {question}"
            )

        LOG.info("confirming the %s", what)
        try:
            return self._postback(self.CONFIRM_YES, wait_for=self.INFO_PANEL)
        except PlaywrightTimeoutError as exc:
            raise error(
                "the site did not answer the confirmation -- check the menu, "
                f"the dish may or may not be {done}"
            ) from exc

    def _click(self, selector: str, wait_for: str) -> None:
        """Click a postback link and wait for the re-rendered page."""
        self.page.wait_for_selector(selector, state="visible")
        self._pause()
        self.page.click(selector)
        self.page.wait_for_selector(wait_for, state="visible")

    def _postback(self, selector: str, wait_for: str) -> str:
        """Click a postback link and return the HTML of the page it loads.

        Unlike :meth:`_click` this waits for the navigation first: after an
        order (or a cancellation) the page still holds the hidden
        ``infoPanel``, which must not be taken for the answer to the next
        click.  ``wait_for`` is looked up only in the complete new page, and
        only needs to be attached.
        """
        self.page.wait_for_selector(selector, state="visible")
        self._pause()
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.page.click(selector)
        self.page.wait_for_selector(wait_for, state="attached")
        return self.page.content()

    def _pause(self) -> None:
        """Wait like a person looking at the page before clicking."""
        if self.options.pause_s > 0:
            time.sleep(random.uniform(0.5, 1.5) * self.options.pause_s)

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
