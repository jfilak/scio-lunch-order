import io
import logging

import pytest
from fake_site import MENU_PAGE

from scio_lunch_order.choosers import ask_user, choose_nothing
from scio_lunch_order.parser import parse_menu


@pytest.fixture(scope="module")
def thursday():
    """čtvrtek 15. října offers dishes 3 and 6."""
    day = parse_menu(MENU_PAGE).days[2]
    assert [item.number for item in day.items] == ["3", "6"]
    return day


def ask(day, answers: str):
    stderr = io.StringIO()
    choice = ask_user(io.StringIO(answers), stderr)(day, day.items)
    return choice, stderr.getvalue()


def test_the_dishes_are_listed_and_the_answer_is_taken(thursday):
    choice, prompt = ask(thursday, "6\n")
    assert choice is thursday.items[1]
    assert "čtvrtek 15. října (2026-10-15) -- vyberte jídlo:" in prompt
    assert "    3. Bulgur se sýrem Halloumi" in prompt
    assert "    6. Kynuté knedlíky s povidly" in prompt
    assert "Číslo jídla (3, 6), Enter = nic: " in prompt


def test_unknown_answers_are_asked_again(thursday):
    choice, prompt = ask(thursday, "1\n3.\n")
    assert choice is thursday.items[0]
    assert "'1' není v nabídce." in prompt


@pytest.mark.parametrize("answers", ["\n", "", "  \n6\n"])
def test_empty_answer_or_end_of_input_chooses_nothing(thursday, answers):
    assert ask(thursday, answers)[0] is None


def test_nobody_to_ask_chooses_nothing(thursday, caplog):
    with caplog.at_level(logging.WARNING):
        assert choose_nothing(thursday, thursday.items) is None
    assert "15. října (2026-10-15) offers 2 dishes and nobody can choose" in caplog.text
