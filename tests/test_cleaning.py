"""Tests for the model-output cleaner (plan §8)."""

import pytest

from momus.cleaning import clean_output

CODE = 'def add(a, b):\n    """Return the sum."""\n    return a + b\n'


def test_plain_answer_is_returned_unchanged_apart_from_edge_blank_lines():
    assert clean_output(f"\n\n{CODE}\n\n") == CODE.rstrip()


def test_first_line_indentation_is_kept():
    assert clean_output("\n    return a + b\n") == "    return a + b"


@pytest.mark.parametrize("opening", ["```", "```python", "```py ", "  ```python"])
def test_markdown_fence_is_stripped(opening):
    assert clean_output(f"{opening}\n{CODE}```\n") == CODE


def test_chatter_around_a_fence_is_stripped():
    reply = f"Here is the code with comments:\n\n```python\n{CODE}```\n\nLet me know if it helps!\n"
    assert clean_output(reply) == CODE


def test_fence_cut_off_before_closing_keeps_what_was_written():
    assert clean_output(f"Sure:\n```python\n{CODE}") == CODE


def test_only_the_first_fenced_block_is_kept():
    reply = f"```python\n{CODE}```\nExample use:\n```python\nadd(1, 2)\n```\n"
    assert clean_output(reply) == CODE


def test_think_block_is_stripped():
    reply = f"<think>\nThe function adds two numbers.\n</think>\n\n{CODE}"
    assert clean_output(reply) == CODE.rstrip()


def test_think_block_and_fence_together():
    reply = f"<think>```not the answer```</think>\nHere:\n```python\n{CODE}```\n"
    assert clean_output(reply) == CODE


def test_unclosed_think_block_leaves_nothing():
    assert clean_output("<think>\nStill reasoning when the tokens ran out") == ""


def test_closing_think_tag_without_opening_drops_what_precedes_it():
    assert clean_output(f"some reasoning\n</think>\n{CODE}") == CODE.rstrip()


def test_chatter_without_a_fence_is_left_for_the_guard():
    # Nothing marks where the sentence ends and the answer starts, so the
    # cleaner does not guess.
    reply = f"Here is the code:\n{CODE}"
    assert clean_output(reply) == reply.rstrip()


def test_non_text_is_refused():
    with pytest.raises(TypeError):
        clean_output(None)
