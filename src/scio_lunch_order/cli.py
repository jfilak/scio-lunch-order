"""Command line entry point: log in, parse the menu, print it."""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
from pathlib import Path

from .browser import DEFAULT_URL, BrowserOptions, LunchSite, LunchSiteError
from .models import Menu, UserInfo
from .parser import ParseError, parse_menu, parse_user
from .render import render_menu, render_user

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
        html = _load_html(args)
        menu = parse_menu(html)
        user = parse_user(html)
    except (LunchSiteError, ParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130

    _print_menu(menu, user, args)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scio-lunch",
        description="Show the school canteen menu and what is already ordered.",
    )
    source = parser.add_argument_group("source")
    source.add_argument(
        "--from-file",
        metavar="PATH",
        type=Path,
        help="parse a saved HTML page instead of opening the site",
    )
    source.add_argument("--url", default=DEFAULT_URL, help=f"site URL (default: {DEFAULT_URL})")
    source.add_argument(
        "-u",
        "--user",
        default=os.environ.get(ENV_USER),
        help=f"user name (default: ${ENV_USER})",
    )
    source.add_argument(
        "--password",
        default=os.environ.get(ENV_PASSWORD),
        help=f"password (default: ${ENV_PASSWORD}, otherwise asked for interactively)",
    )

    browser = parser.add_argument_group("browser")
    browser.add_argument("--headed", action="store_true", help="show the browser window")
    browser.add_argument(
        "--slow-mo",
        type=int,
        default=0,
        metavar="MS",
        help="slow every Playwright action down, for watching the run",
    )
    browser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="per-step timeout (default: 30)",
    )
    browser.add_argument(
        "--insecure",
        action="store_true",
        help="accept an invalid HTTPS certificate",
    )

    output = parser.add_argument_group("output")
    output.add_argument("--json", action="store_true", help="print JSON instead of text")
    output.add_argument(
        "--save-html",
        metavar="PATH",
        type=Path,
        help="write the downloaded page to a file (useful for debugging)",
    )
    output.add_argument(
        "--screenshot",
        metavar="PATH",
        type=Path,
        help="write a screenshot of the menu page to a file",
    )
    output.add_argument("--no-color", action="store_true", help="disable ANSI colours")
    output.add_argument("-v", "--verbose", action="store_true", help="log every step")

    args = parser.parse_args(argv)
    if args.from_file is None and not args.user:
        parser.error(f"a user name is required: pass --user or set ${ENV_USER}")
    return args


def _load_html(args: argparse.Namespace) -> str:
    if args.from_file:
        LOG.info("reading %s", args.from_file)
        return args.from_file.read_text(encoding="utf-8")

    options = BrowserOptions(
        url=args.url,
        headless=not args.headed,
        timeout_ms=int(args.timeout * 1000),
        slow_mo_ms=args.slow_mo,
        ignore_https_errors=args.insecure,
    )
    password = args.password or _ask_password(args.user)

    with LunchSite(options) as site:
        site.open()
        site.login(args.user, password)
        html = site.menu_html()
        if args.screenshot:
            site.screenshot(str(args.screenshot))
            LOG.info("screenshot written to %s", args.screenshot)

    if args.save_html:
        args.save_html.write_text(html, encoding="utf-8")
        LOG.info("page written to %s", args.save_html)
    return html


def _ask_password(user: str) -> str:
    if not sys.stdin.isatty():
        raise LunchSiteError(
            f"no password given -- set ${ENV_PASSWORD} or use --password"
        )
    return getpass.getpass(f"Password for {user}: ")


def _print_menu(menu: Menu, user: UserInfo | None, args: argparse.Namespace) -> None:
    if args.json:
        data = {"user": user.to_dict() if user else None, **menu.to_dict()}
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return

    color = not args.no_color and sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    if user is not None:
        sys.stdout.write(render_user(user, color=color) + "\n")
    sys.stdout.write(render_menu(menu, color=color))


if __name__ == "__main__":
    raise SystemExit(main())
