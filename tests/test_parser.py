from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from scio_lunch_order.parser import (
    ParseError,
    parse_confirm_message,
    parse_info_message,
    parse_menu,
    parse_user,
)

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="module")
def ordered():
    """A week where every 'Oběd 3' is already ordered."""
    return parse_menu((DATA / "menu_ordered.html").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def not_ordered():
    """The same week with nothing ordered."""
    return parse_menu((DATA / "menu_not_ordered.html").read_text(encoding="utf-8"))


def test_all_days_are_found(ordered):
    assert [day.date for day in ordered.days] == [
        date(2026, 9, 21),
        date(2026, 9, 22),
        date(2026, 9, 23),
        date(2026, 9, 24),
        date(2026, 9, 25),
    ]


def test_day_label_excludes_the_anchor(ordered):
    assert ordered.days[0].label == "zítra, 21. září"
    assert ordered.days[1].label == "úterý 22. září"


def test_options_are_grouped_under_their_day(ordered):
    assert [option.name for option in ordered.days[0].options] == ["Oběd 3"]
    assert [option.name for option in ordered.days[2].options] == ["Oběd 3", "Oběd 6"]


def test_soup_is_read_from_the_header(ordered):
    option = ordered.days[0].options[0]
    assert option.soup == "Polévka vývar s nudlemi a zeleninou (3,9)"
    assert option.soup_allergens == []

    lentil = ordered.days[1].options[0]
    assert lentil.soup == "Polévka čočková"
    assert lentil.soup_allergens == ["1-lepek"]


def test_food_item_details(ordered):
    item = ordered.days[0].options[0].items[0]
    assert item.number == "3"
    assert item.label == (
        "Vepřové maso po námořnicku (rajský protlak, vejce) "
        "(lepek 1.1,3), těstoviny 1,3"
    )
    assert item.allergens == ["1-lepek"]


def test_allergen_span_is_cut_out_of_the_middle_of_the_label(ordered):
    item = ordered.days[1].options[0].items[0]
    assert item.label.endswith("bramborová kaše 7, kompot")
    assert "mléko" not in item.label
    assert item.allergens == ["7-mléko"]


def test_multiple_allergens_in_one_span(ordered):
    item = ordered.days[4].options[0].items[0]
    assert item.allergens == ["1-lepek", "3-vejce"]


def test_ordered_items_are_detected(ordered):
    assert len(ordered.ordered_items) == 5
    assert all(day.ordered for day in ordered.days)
    for day in ordered.days:
        assert day.options[0].ordered, day.label
        for option in day.options[1:]:
            assert not option.ordered, day.label


def test_nothing_is_ordered_in_the_plain_page(not_ordered):
    assert not_ordered.ordered_items == []
    assert len(not_ordered.items) == 8
    assert all(item.can_order for item in not_ordered.items)
    assert not any(item.can_cancel for item in not_ordered.items)


def test_actions_carry_the_element_id_and_postback_target(ordered):
    item = ordered.days[0].options[0].items[0]
    assert item.order_action.element_id == (
        "repeaterDays_ctl00_repeaterFoodType_ctl00_repeaterFood_ctl00_btnFood"
    )
    assert item.order_action.postback_target == (
        "repeaterDays$ctl00$repeaterFoodType$ctl00$repeaterFood$ctl00$btnFood"
    )
    assert item.cancel_action.element_id.endswith("btnFood2")
    assert item.cancel_action.label == "Zrušit objednávku"


def test_item_without_a_cancel_link_is_not_ordered(ordered):
    item = ordered.days[2].options[1].items[0]
    assert item.label == "Játrová omáčka(1), dušená rýže"
    assert item.ordered is False
    assert item.can_order is True
    assert item.can_cancel is False


def test_menu_can_be_serialised(ordered):
    data = ordered.to_dict()
    assert data["summary"] == {"days": 5, "items": 8, "ordered": 5}
    assert data["days"][0]["date"] == "2026-09-21"
    assert data["days"][0]["options"][0]["items"][0]["ordered"] is True


def test_a_page_without_the_menu_is_rejected():
    with pytest.raises(ParseError):
        parse_menu("<html><body><div id='login'></div></body></html>")


def test_menu_without_days_is_empty():
    assert parse_menu('<div class="warea"></div>').days == []


def test_block_without_a_header_still_yields_an_item():
    html = """
    <div class="warea">
      <div class="fblock">
        <div class="food--label">Guláš</div>
        <div class="fcmd"><a id="b1" href="javascript:__doPostBack('x','')">Objednat</a></div>
      </div>
    </div>
    """
    menu = parse_menu(html)
    assert [item.label for item in menu.items] == ["Guláš"]


USRBLOCK = """
<div>
<span id="lblHeadr" class="usrblock__user">Hynek Filák</span>
</div>
<div>
<span id="lblUserSpec" class="usrblock__userparam">Stav účtu:&nbsp;{credit}</span>
</div>
"""


def test_user_info_is_parsed():
    user = parse_user(USRBLOCK.format(credit="135 Kč"))
    assert user is not None
    assert user.full_name == "Hynek Filák"
    assert user.credit == Decimal("135")


@pytest.mark.parametrize(
    ("credit", "expected"),
    [
        ("0 Kč", Decimal("0")),
        ("-42 Kč", Decimal("-42")),
        ("1&nbsp;235,50 Kč", Decimal("1235.50")),
        ("1 235 Kč", Decimal("1235")),
    ],
)
def test_user_credit_formats(credit, expected):
    assert parse_user(USRBLOCK.format(credit=credit)).credit == expected


def test_user_credit_missing_or_unexpected():
    assert parse_user(USRBLOCK.format(credit="neznámý")).credit is None
    html = '<span class="usrblock__user">Hynek Filák</span>'
    assert parse_user(html).credit is None


def test_no_user_on_menu_fragment():
    assert parse_user((DATA / "menu_ordered.html").read_text(encoding="utf-8")) is None


def test_confirmation_question_is_read_from_the_dialog():
    html = (DATA / "order_confirm.html").read_text(encoding="utf-8")
    assert parse_confirm_message(html) == (
        "Opravdu si přejete objednat rybí nugetky z tresky (1,4,3) "
        "dne pátek 16. října 2026, jídelna Jídelna?"
    )
    assert parse_info_message(html) is None


def test_info_popup_is_read_although_it_gets_hidden():
    html = (DATA / "order_done.html").read_text(encoding="utf-8")
    assert parse_info_message(html) == "Vaše objednávka byla úspěšně provedena"
    assert parse_confirm_message(html) is None


def test_plain_menu_has_no_dialog_or_popup():
    html = (DATA / "menu_ordered.html").read_text(encoding="utf-8")
    assert parse_confirm_message(html) is None
    assert parse_info_message(html) is None
