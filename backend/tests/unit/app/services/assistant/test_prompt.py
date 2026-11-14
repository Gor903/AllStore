"""What the assistant is told about itself.

The rules are the product plan's: the assistant may not invent availability, price,
characteristics, the seller or delivery terms. It cannot invent the cards — it never sees a
product it did not ask the catalogue for — so the prompt only has to hold the text back from
describing things a shop like this merely tends to have.

Short on purpose, and the length was measured rather than guessed: a 3B model on the stand
answers a general question with silence once the prompt grows. At six rules «Что подарить
ребёнку 3 лет?» returned nothing at every temperature, and one more rule cost the right tool
on «небольшая белая ваза». So this test guards the length as a property, not as trivia —
whatever the code already enforces stays out of the prompt.
"""

from app.services.assistant.prompt import SYSTEM_PROMPT

# measured on the stand: above this, a 3B model started answering general questions with
# silence. Raising it is a decision that needs the same measurement again.
MAX_LINES = 8


def test_the_assistant_is_told_what_it_is() -> None:
    assert "AllStore" in SYSTEM_PROMPT


def test_it_is_told_to_search_before_answering_even_a_general_question() -> None:
    """The silence being guarded against was exactly this: a general question answered from
    the model's own idea of what a shop sells."""
    assert "всегда" in SYSTEM_PROMPT


def test_it_is_told_not_to_invent_the_things_a_shop_merely_tends_to_have() -> None:
    for forbidden in ("цены", "наличие", "магазины", "доставку"):
        assert forbidden in SYSTEM_PROMPT


def test_it_is_told_what_to_say_when_the_search_found_nothing() -> None:
    """Otherwise a model fills the silence, which is the one thing it must not do here."""
    assert "ничего не вернул" in SYSTEM_PROMPT


def test_it_is_told_which_of_the_two_searches_to_use() -> None:
    assert "exact_search" in SYSTEM_PROMPT
    assert "semantic_search" in SYSTEM_PROMPT


def test_it_is_told_to_answer_in_the_language_the_platform_speaks() -> None:
    assert "по-русски" in SYSTEM_PROMPT


def test_it_stays_short_enough_for_the_model_on_the_stand() -> None:
    lines = [line for line in SYSTEM_PROMPT.splitlines() if line.strip()]

    assert len(lines) <= MAX_LINES, "measured, not guessed — see the module docstring"
