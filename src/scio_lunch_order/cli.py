"""Command line entry point: log in, then print the menu or order dishes."""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError

from .browser import DEFAULT_URL, BrowserOptions, LunchSite, LunchSiteError
from .choosers import Chooser, ask_user, choose_nothing
from .models import Menu, OrderResult, UserInfo
from .ordering import choose_dishes, order_chosen, order_dish
from .parser import ParseError, parse_menu, parse_user
from .render import render_menu, render_order_result, render_order_results, render_user
from .selection import SelectionError, parse_day_spec, parse_item_spec

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
        elif args.command == "order-all":
            results, credit_before, credit_after = _order_all(args)
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
    elif args.command == "order-all":
        _print_order_all(results, credit_before, credit_after, args)
        return 1 if any(result.status == OrderResult.FAILED for result in results) else 0
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

    order_all = commands.add_parser(
        "order-all",
        help="order every day that has nothing ordered yet",
        description=(
            "Order every day of the menu that has nothing ordered yet. A day with a "
            "single dish gets it, for a day with more dishes you are asked which one. "
            "All questions come first, then the days are ordered one after another."
        ),
    )
    order_all.add_argument_group("order").add_argument(
        "--dry-run",
        action="store_true",
        help="log in and choose the dishes, but do not order them",
    )
    _add_common_arguments(order_all, suppress=True)

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
        help="parse a saved HTML page instead of opening the site; nothing gets ordered",
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
        "--pause",
        type=float,
        default=default(2.0),
        metavar="SECONDS",
        help="average pause before every click, to use the site at a human pace (default: 2)",
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
        html = args.from_file.read_text(encoding="utf-8")
        return order_dish(None, html, args.day, args.item)[0]

    password = args.password or _ask_password(args.user)
    with LunchSite(_browser_options(args)) as site:
        site.open()
        site.login(args.user, password)
        result, html = order_dish(site, site.menu_html(), args.day, args.item, dry_run=args.dry_run)
        _keep_page(site, html, args)
    return result


def _order_all(
    args: argparse.Namespace,
) -> tuple[list[OrderResult], Decimal | None, Decimal | None]:
    """Order every day; returns the results and the credit before and after."""
    choose = _chooser()
    if args.from_file:
        LOG.info("reading %s, nothing will be ordered", args.from_file)
        html = args.from_file.read_text(encoding="utf-8")
        results = order_chosen(None, html, choose_dishes(parse_menu(html), choose))
        return results, _credit_of(html), None

    password = args.password or _ask_password(args.user)
    with LunchSite(_browser_options(args)) as site:
        site.open()
        site.login(args.user, password)
        html = site.menu_html()
        credit_before = _credit_of(html)
        plan = choose_dishes(parse_menu(html), choose)
        if not args.dry_run and any(planned.status == OrderResult.CHOSEN for planned in plan):
            # Answering may have taken a while and the site logs idle users
            # out: log in again if needed and start from a fresh menu.
            site.login(args.user, password)
            html = site.menu_html()
        results = order_chosen(site, html, plan, dry_run=args.dry_run)
        # Whatever happens to the browser now, the results must be reported.
        try:
            html = site.page.content()
            _keep_page(site, html, args)
        except PlaywrightError:
            LOG.warning("cannot read the final page", exc_info=args.verbose)
            return results, credit_before, None
    return results, credit_before, _credit_of(html)


def _chooser() -> Chooser:
    """Ask on the terminal; without one, days with a choice are skipped."""
    return ask_user() if sys.stdin.isatty() else choose_nothing


def _credit_of(html: str) -> Decimal | None:
    user = parse_user(html)
    return user.credit if user else None


def _browser_options(args: argparse.Namespace) -> BrowserOptions:
    return BrowserOptions(
        url=args.url,
        headless=not args.headed,
        timeout_ms=int(args.timeout * 1000),
        slow_mo_ms=args.slow_mo,
        ignore_https_errors=args.insecure,
        pause_s=args.pause,
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


def _print_order_all(
    results: list[OrderResult],
    credit_before: Decimal | None,
    credit_after: Decimal | None,
    args: argparse.Namespace,
) -> None:
    if args.json:
        _print_json(
            {
                "days": [result.to_dict() for result in results],
                "credit_before": str(credit_before) if credit_before is not None else None,
                "credit_after": str(credit_after) if credit_after is not None else None,
            }
        )
        return
    text = render_order_results(
        results,
        credit_before=credit_before,
        credit_after=credit_after,
        color=_use_color(args),
    )
    sys.stdout.write(text)


def _print_json(data: dict[str, Any]) -> None:
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _use_color(args: argparse.Namespace) -> bool:
    return not args.no_color and sys.stdout.isatty() and not os.environ.get("NO_COLOR")


if __name__ == "__main__":
    raise SystemExit(main())
