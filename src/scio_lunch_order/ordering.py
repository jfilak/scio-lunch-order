"""Ordering and cancelling on a logged-in :class:`~.browser.LunchSite`.

``order`` and ``cancel`` handle the dish of one day.  ``order-all`` works in
two steps, so that the site is not touched while the user (or another
:data:`~.choosers.Chooser`) decides:

1. :func:`choose_dishes` picks the dish of every day that has nothing ordered:
   a day with a single dish takes it, otherwise the chooser is asked.
2. :func:`order_chosen` orders them strictly one day after another, each from
   the menu the previous order ended on.  The first failure of the site stops
   the run -- the state of the page is unknown then.

``cancel-all`` is the same without questions: :func:`plan_cancellations`
lists every ordered dish, :func:`cancel_chosen` cancels them one by one.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace

from playwright.sync_api import Error as PlaywrightError

from .browser import CancelError, LunchSite, LunchSiteError, OrderError
from .choosers import Chooser
from .models import Menu, OrderResult
from .parser import ParseError, parse_info_message, parse_menu, parse_user
from .selection import (
    DaySpec,
    SelectionError,
    czech_date,
    day_spec_for,
    describe_day,
    ensure_cancellable,
    ensure_orderable,
    find_item,
    find_ordered_item,
)

LOG = logging.getLogger(__name__)


def order_dish(
    site: LunchSite | None,
    html: str,
    day_spec: DaySpec,
    number: str,
    *,
    dry_run: bool = False,
) -> tuple[OrderResult, str]:
    """Order one dish of the menu page ``html``.

    Without a ``site`` (or with ``dry_run``) the dish is only looked up.
    Returns the result and the HTML of the page the site ended on.
    """
    day, item = find_item(parse_menu(html), day_spec, number)
    user = parse_user(html)
    credit_before = user.credit if user else None

    # An ordered dish still has its 'Objednat' link; clicking it again would
    # most likely order a second portion.
    if item.ordered:
        LOG.info("dish %s of %s is already ordered", item.number, describe_day(day))
        result = OrderResult(OrderResult.ALREADY_ORDERED, day, item, credit_before=credit_before)
        return result, html
    ensure_orderable(day, item)
    if site is None or dry_run:
        return OrderResult(OrderResult.DRY_RUN, day, item, credit_before=credit_before), html

    html = site.order(item.order_action, expected_date=czech_date(day.date))
    message = parse_info_message(html)
    # The popup alone proves nothing: the dish must be marked as ordered now.
    try:
        _day, item = find_item(parse_menu(html), day_spec, number)
    except SelectionError as exc:
        raise OrderError(f"the dish is gone from the page after the order: {exc}") from exc
    if not item.ordered:
        raise OrderError(
            f"the site answered {message!r}, but the dish is not marked as ordered"
        )

    user = parse_user(html)
    result = OrderResult(
        OrderResult.ORDERED,
        day,
        item,
        message=message,
        credit_before=credit_before,
        credit_after=user.credit if user else None,
    )
    return result, html


def cancel_dish(
    site: LunchSite | None,
    html: str,
    day_spec: DaySpec,
    number: str | None = None,
    *,
    dry_run: bool = False,
) -> tuple[OrderResult, str]:
    """Cancel the order of a dish of the menu page ``html``.

    Without a ``number`` it is the dish ordered on that day.  Without a
    ``site`` (or with ``dry_run``) the dish is only looked up.  Returns the
    result and the HTML of the page the site ended on.
    """
    day, item = find_ordered_item(parse_menu(html), day_spec, number)
    user = parse_user(html)
    credit_before = user.credit if user else None

    if item is None or not item.ordered:
        LOG.info("nothing to cancel on %s", describe_day(day))
        return OrderResult(OrderResult.NOT_ORDERED, day, item, credit_before=credit_before), html
    ensure_cancellable(day, item)
    if site is None or dry_run:
        return OrderResult(OrderResult.DRY_RUN, day, item, credit_before=credit_before), html

    html = site.cancel(item.cancel_action, expected_date=czech_date(day.date))
    message = parse_info_message(html)
    # As with an order, only the menu itself proves the cancellation.
    try:
        _day, item = find_item(parse_menu(html), day_spec, item.number)
    except SelectionError as exc:
        raise CancelError(f"the dish is gone from the page after the cancellation: {exc}") from exc
    if item.ordered:
        raise CancelError(
            f"the site answered {message!r}, but the dish is still marked as ordered"
        )

    user = parse_user(html)
    result = OrderResult(
        OrderResult.CANCELLED,
        day,
        item,
        message=message,
        credit_before=credit_before,
        credit_after=user.credit if user else None,
    )
    return result, html


def choose_dishes(menu: Menu, choose: Chooser) -> list[OrderResult]:
    """The plan of ``order-all``: one result per day, ``CHOSEN`` to be ordered."""
    plan = []
    for day in menu.days:
        if day.ordered:
            plan.append(OrderResult(OrderResult.ALREADY_ORDERED, day, day.ordered_items[0]))
            continue
        dishes = [item for item in day.items if item.can_order and item.number]
        if day.date is None or not dishes:
            plan.append(OrderResult(OrderResult.SKIPPED, day, None, message="není co objednat"))
            continue
        if len(dishes) == 1:
            plan.append(OrderResult(OrderResult.CHOSEN, day, dishes[0]))
            continue

        item = choose(day, dishes)
        if item is None:
            plan.append(OrderResult(OrderResult.SKIPPED, day, None, message="nic nevybráno"))
        elif item not in dishes:
            raise SelectionError(f"the chooser picked a dish not offered on {describe_day(day)}")
        else:
            plan.append(OrderResult(OrderResult.CHOSEN, day, item))
    return plan


def plan_cancellations(menu: Menu) -> list[OrderResult]:
    """The plan of ``cancel-all``: every ordered dish, ``CHOSEN`` to be cancelled."""
    plan = []
    for day in menu.days:
        if not day.ordered:
            plan.append(OrderResult(OrderResult.NOT_ORDERED, day, None))
            continue
        for item in day.ordered_items:
            if not item.can_cancel:
                message = "objednávku už nelze zrušit"
                plan.append(OrderResult(OrderResult.SKIPPED, day, item, message=message))
            elif day.date is None or not item.number:
                message = "jídlo nelze na stránce najít"
                plan.append(OrderResult(OrderResult.SKIPPED, day, item, message=message))
            else:
                plan.append(OrderResult(OrderResult.CHOSEN, day, item))
    return plan


def order_chosen(
    site: LunchSite | None,
    html: str,
    plan: list[OrderResult],
    *,
    dry_run: bool = False,
) -> list[OrderResult]:
    """Order the ``CHOSEN`` days of ``plan``, one after another.

    Every day is looked up again in the page the previous order ended on, so
    its link and its state are current.  A day refused before the click (the
    menu changed meanwhile) fails alone; a failure of the site stops the run.
    """

    def order(html: str, planned: OrderResult) -> tuple[OrderResult, str]:
        day_spec = day_spec_for(planned.day.date)
        return order_dish(site, html, day_spec, planned.item.number, dry_run=dry_run)

    return _carry_out(html, plan, order, "ordering")


def cancel_chosen(
    site: LunchSite | None,
    html: str,
    plan: list[OrderResult],
    *,
    dry_run: bool = False,
) -> list[OrderResult]:
    """Cancel the ``CHOSEN`` dishes of ``plan``, one after another.

    Works like :func:`order_chosen`.
    """

    def cancel(html: str, planned: OrderResult) -> tuple[OrderResult, str]:
        day_spec = day_spec_for(planned.day.date)
        return cancel_dish(site, html, day_spec, planned.item.number, dry_run=dry_run)

    return _carry_out(html, plan, cancel, "cancelling")


def _carry_out(
    html: str,
    plan: list[OrderResult],
    step: Callable[[str, OrderResult], tuple[OrderResult, str]],
    doing: str,
) -> list[OrderResult]:
    """Run ``step`` for every ``CHOSEN`` result of ``plan``, from page ``html`` on.

    ``step`` gets the current page and the planned result, and returns the
    final result and the page it ended on.
    """
    results = []
    stopped = False
    for planned in plan:
        if planned.status != OrderResult.CHOSEN:
            results.append(planned)
            continue
        if stopped:
            results.append(
                replace(planned, status=OrderResult.SKIPPED, message="nezkoušeno kvůli chybě")
            )
            continue

        LOG.info("%s dish %s of %s", doing, planned.item.number, describe_day(planned.day))
        try:
            result, html = step(html, planned)
        except SelectionError as exc:
            result = replace(planned, status=OrderResult.FAILED, message=str(exc))
        except (LunchSiteError, ParseError, PlaywrightError) as exc:
            LOG.debug("stopping after a failure of %s", doing, exc_info=True)
            result = replace(planned, status=OrderResult.FAILED, message=str(exc))
            stopped = True
        results.append(result)
    return results
