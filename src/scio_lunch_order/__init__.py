"""Automated ordering of school lunches on the ASP.NET canteen site."""

from .choosers import Chooser, ask_user, choose_nothing
from .models import Action, Day, FoodItem, Menu, MenuOption, OrderResult, UserInfo
from .parser import ParseError, parse_menu, parse_user
from .render import (
    render_cancel_result,
    render_cancel_results,
    render_menu,
    render_order_result,
    render_order_results,
    render_user,
)
from .selection import (
    SelectionError,
    find_day,
    find_item,
    find_ordered_item,
    parse_day_spec,
    parse_item_spec,
)

__version__ = "0.1.0"

__all__ = [
    "Action",
    "Chooser",
    "Day",
    "FoodItem",
    "Menu",
    "MenuOption",
    "OrderResult",
    "ParseError",
    "SelectionError",
    "UserInfo",
    "ask_user",
    "choose_nothing",
    "find_day",
    "find_item",
    "find_ordered_item",
    "parse_day_spec",
    "parse_item_spec",
    "parse_menu",
    "parse_user",
    "render_cancel_result",
    "render_cancel_results",
    "render_menu",
    "render_order_result",
    "render_order_results",
    "render_user",
]
