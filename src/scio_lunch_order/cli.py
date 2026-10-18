"""Command line entry point: log in, then print the menu or order a dish."""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .browser import DEFAULT_URL, BrowserOptions, LunchSite, LunchSiteError, OrderError
from .models import Menu, OrderResult, UserInfo
from .parser import ParseError, parse_info_message, parse_menu, parse_user
from .render import render_menu, render_order_result, render_user
from .selection import (
    SelectionError,
    czech_date,
    ensure_orderable,
    find_item,
    parse_day_spec,
    parse_item_spec,
)

ENV_USER = "SCIO_LUNCH_USER"
ENV_PASSWORD = "SCIO_LUNCH_PASSWORD"

LOG = logging.getLogger("scio_lunch_order")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        if args.command == "order":
            result = _order(args)
        else:
            html = _load_html(args)
            menu = parse_menu(html)
            user = parse_user(html)
    except (LunchSiteError, ParseError, SelectionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130

    if args.command == "order":
        _print_order(result, args)
    else:
        _print_menu(menu, user, args)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scio-lunch",
        description="Show the school canteen menu and what is already ordered.",
    )
    _add_common_arguments(parser)

    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    order = commands.add_parser(
        "order",
        help="order one dish for one day",
        description="Order one dish for one day. A dish that is already ordered is left alone.",
    )
    wanted = order.add_argument_group("order")
    wanted.add_argument(
        "--day",
        required=True,
        type=_argument_type(parse_day_spec),
        help="the day: 2026-10-16, 16.10.2026 or 'pátek 16. října'",
    )
    wanted.add_argument(
        "--item",
        required=True,
        type=_argument_type(parse_item_spec),
        metavar="N",
        help="the dish number shown in the menu, e.g. 3 or 6",
    )
    wanted.add_argument(
        "--dry-run",
        action="store_true",
        help="log in and find the dish, but do not order it",
    )
    _add_common_arguments(order, suppress=True)

    args = parser.parse_args(argv)
    if args.from_file is None and not args.user:
        parser.error(f"a user name is required: pass --user or set ${ENV_USER}")
    return args


def _add_common_arguments(parser: argparse.ArgumentParser, suppress: bool = False) -> None:
    """Options of every command, accepted before and after the command name.

    ``suppress`` is for sub-parsers: their defaults would otherwise overwrite
    the values given before the command name.
    """

    def default(value: Any) -> Any:
        return argparse.SUPPRESS if suppress else value

    source = parser.add_argument_group("source")
    source.add_argument(
        "--from-file",
        metavar="PATH",
        type=Path,
        default=default(None),
        help="parse a saved HTML page instead of opening the site; 'order' then orders nothing",
    )
    source.add_argument(
        "--url",
        default=default(DEFAULT_URL),
        help=f"site URL (default: {DEFAULT_URL})",
    )
    source.add_argument(
        "-u",
        "--user",
        default=default(os.environ.get(ENV_USER)),
        help=f"user name (default: ${ENV_USER})",
    )
    source.add_argument(
        "--password",
        default=default(os.environ.get(ENV_PASSWORD)),
        help=f"password (default: ${ENV_PASSWORD}, otherwise asked for interactively)",
    )

    browser = parser.add_argument_group("browser")
    browser.add_argument(
        "--headed",
        action="store_true",
        default=default(False),
        help="show the browser window",
    )
    browser.add_argument(
        "--slow-mo",
        type=int,
        default=default(0),
        metavar="MS",
        help="slow every Playwright action down, for watching the run",
    )
    browser.add_argument(
        "--timeout",
        type=float,
        default=default(30.0),
        metavar="SECONDS",
        help="per-step timeout (default: 30)",
    )
    browser.add_argument(
        "--insecure",
        action="store_true",
        default=default(False),
        help="accept an invalid HTTPS certificate",
    )

    output = parser.add_argument_group("output")
    output.add_argument(
        "--json",
        action="store_true",
        default=default(False),
        help="print JSON instead of text",
    )
    output.add_argument(
        "--save-html",
        metavar="PATH",
        type=Path,
        default=default(None),
        help="write the downloaded page to a file (useful for debugging)",
    )
    output.add_argument(
        "--screenshot",
        metavar="PATH",
        type=Path,
        default=default(None),
        help="write a screenshot of the menu page to a file",
    )
    output.add_argument(
        "--no-color",
        action="store_true",
        default=default(False),
        help="disable ANSI colours",
    )
    output.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=default(False),
        help="log every step",
    )


def _argument_type(parse: Callable[[str], Any]) -> Callable[[str], Any]:
    """Report a :class:`SelectionError` as an argparse usage error."""

    def convert(text: str) -> Any:
        try:
            return parse(text)
        except SelectionError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from exc

    return convert


def _load_html(args: argparse.Namespace) -> str:
    if args.from_file:
        LOG.info("reading %s", args.from_file)
        return args.from_file.read_text(encoding="utf-8")

    password = args.password or _ask_password(args.user)
    with LunchSite(_browser_options(args)) as site:
        site.open()
        site.login(args.user, password)
        html = site.menu_html()
        _keep_page(site, html, args)
    return html


def _order(args: argparse.Namespace) -> OrderResult:
    if args.from_file:
        LOG.info("reading %s, nothing will be ordered", args.from_file)
        return _order_on_page(None, args.from_file.read_text(encoding="utf-8"), args)

    password = args.password or _ask_password(args.user)
    with LunchSite(_browser_options(args)) as site:
        site.open()
        site.login(args.user, password)
        result = _order_on_page(site, site.menu_html(), args)
        _keep_page(site, site.page.content(), args)
    return result


def _order_on_page(site: LunchSite | None, html: str, args: argparse.Namespace) -> OrderResult:
    """Order the requested dish of the menu page ``html``.

    Without a ``site`` (or with --dry-run) the dish is only looked up.
    """
    day, item = find_item(parse_menu(html), args.day, args.item)
    user = parse_user(html)
    credit_before = user.credit if user else None

    # An ordered dish still has its 'Objednat' link; clicking it again would
    # most likely order a second portion.
    if item.ordered:
        LOG.info("dish %s is already ordered", item.number)
        return OrderResult(OrderResult.ALREADY_ORDERED, day, item, credit_before=credit_before)
    ensure_orderable(day, item)
    if site is None or args.dry_run:
        return OrderResult(OrderResult.DRY_RUN, day, item, credit_before=credit_before)

    html = site.order(item.order_action, expected_date=czech_date(day.date))
    message = parse_info_message(html)
    # The popup alone proves nothing: the dish must be marked as ordered now.
    try:
        _day, item = find_item(parse_menu(html), args.day, args.item)
    except SelectionError as exc:
        raise OrderError(f"the dish is gone from the page after the order: {exc}") from exc
    if not item.ordered:
        raise OrderError(
            f"the site answered {message!r}, but the dish is not marked as ordered"
        )

    user = parse_user(html)
    return OrderResult(
        OrderResult.ORDERED,
        day,
        item,
        message=message,
        credit_before=credit_before,
        credit_after=user.credit if user else None,
    )


def _browser_options(args: argparse.Namespace) -> BrowserOptions:
    return BrowserOptions(
        url=args.url,
        headless=not args.headed,
        timeout_ms=int(args.timeout * 1000),
        slow_mo_ms=args.slow_mo,
        ignore_https_errors=args.insecure,
    )


def _keep_page(site: LunchSite, html: str, args: argparse.Namespace) -> None:
    """Write --screenshot and --save-html of the page the run ended on."""
    if args.screenshot:
        site.screenshot(str(args.screenshot))
        LOG.info("screenshot written to %s", args.screenshot)
    if args.save_html:
        args.save_html.write_text(html, encoding="utf-8")
        LOG.info("page written to %s", args.save_html)


def _ask_password(user: str) -> str:
    if not sys.stdin.isatty():
        raise LunchSiteError(
            f"no password given -- set ${ENV_PASSWORD} or use --password"
        )
    return getpass.getpass(f"Password for {user}: ")


def _print_menu(menu: Menu, user: UserInfo | None, args: argparse.Namespace) -> None:
    if args.json:
        _print_json({"user": user.to_dict() if user else None, **menu.to_dict()})
        return

    color = _use_color(args)
    if user is not None:
        sys.stdout.write(render_user(user, color=color) + "\n")
    sys.stdout.write(render_menu(menu, color=color))


def _print_order(result: OrderResult, args: argparse.Namespace) -> None:
    if args.json:
        _print_json(result.to_dict())
        return
    sys.stdout.write(render_order_result(result, color=_use_color(args)))


def _print_json(data: dict[str, Any]) -> None:
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _use_color(args: argparse.Namespace) -> bool:
    return not args.no_color and sys.stdout.isatty() and not os.environ.get("NO_COLOR")


if __name__ == "__main__":
    raise SystemExit(main())
