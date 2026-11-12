"""Tests for the deterministic quality rules (plan §9)."""

import pytest

from momus import clio
from momus.backends.fake import FakeBackend
from momus.quality import comment_problem, is_placeholder, polish_docstring

RETRY = (
    "def retry(func, attempts=3):\n"
    "    last = None\n"
    "    for attempt in range(attempts):\n"
    "        try:\n"
    "            return func()\n"
    "        except OSError as error:\n"
    "            last = error\n"
    "    raise last\n"
)


# --- Docstrings ------------------------------------------------------------


def test_headings_get_one_spelling_and_entries_lose_bullets_and_backticks():
    text = "Do it.\nArguments:\n- `func`: What to call.\n- n (int): How often.\nExceptions:\n- ValueError: If bad."
    assert polish_docstring(text) == (
        "Do it.\n\nArgs:\n    func: What to call.\n    n (int): How often.\n\n"
        "Raises:\n    ValueError: If bad."
    )


@pytest.mark.parametrize(
    "text",
    [
        "Do it.\n\nReturns:\nNone",
        "Do it.\n\nReturns: None",
        "Do it.\n\nExceptions:\nNo exceptions are raised.",
        "Do it.\n\nRaises:\n- None",
        "Do it.\n\nArgs:\n- self: The instance of the class.",
    ],
)
def test_sections_that_say_nothing_are_dropped_entirely(text):
    assert polish_docstring(text) == "Do it."


def test_a_vacuous_entry_goes_but_the_useful_ones_stay():
    text = "Do it.\n\nArgs:\n- self: The instance.\n- n: How often."
    assert polish_docstring(text) == "Do it.\n\nArgs:\n    n: How often."


def test_inline_heading_text_and_plain_prose_are_left_alone():
    text = "Do it.\n\nIt has a note: take care.\nReturns: the value."
    assert polish_docstring(text) == text


def test_other_headings_are_indented_but_their_content_is_kept():
    assert polish_docstring("Do it.\nExample:\nretry(f)\nNote:\nNone") == (
        "Do it.\n\nExample:\n    retry(f)\n\nNote:\n    None"
    )


def test_a_long_single_paragraph_gets_a_summary_line():
    text = (
        "Calculates the total value of all items in the inventory. It sums the quantity times "
        "the unit price of every item."
    )
    assert polish_docstring(text) == (
        "Calculates the total value of all items in the inventory.\n\n"
        "It sums the quantity times the unit price of every item."
    )


@pytest.mark.parametrize(
    "text",
    [
        "Returns the total.",  # short: stays one line
        "Calculates the total value of all items in the inventory without any trailing sentence",
        "Do it.\n\nWith a second paragraph that is quite long and goes on for a while, past the limit.",
    ],
)
def test_a_docstring_that_already_has_a_summary_or_fits_is_not_split(text):
    assert polish_docstring(text) == text


def test_polishing_is_idempotent():
    once = polish_docstring("Do it. Then rest.\nArguments:\n- `a`: b\nReturns:\nNone")
    assert polish_docstring(once) == once


@pytest.mark.parametrize(
    "text",
    ["<the docstring text>", "The comment text is missing.", "The docstring text goes here."],
)
def test_a_template_echoed_back_is_a_placeholder(text):
    assert is_placeholder(text)
    assert not is_placeholder("Return the sum of a and b.")


def test_placeholder_docstring_reply_is_rejected_and_nothing_is_inserted():
    result = clio.comment_source("def a():\n    pass\n", FakeBackend(["DOCSTRING:\n<the docstring text>"]), "docstrings")
    assert result.text == "def a():\n    pass\n"
    assert (result.outcomes[0].status, result.outcomes[0].cause) == ("rejected", "reply")


# --- Comments --------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "statement"),
    [
        ("The comment text is missing.", "x = 1"),
        ("This checks if the input list is empty.", "if not values:"),
        ("This function calculates the mean.", "total = sum(values)"),
        ("The `clamp` function takes three arguments.", "return max(low, v)"),
        ("It returns the middle element.", "return ordered[middle]"),
        ("window must be at least 1", 'if window < 1:\n    raise ValueError("window must be at least 1")'),
        ("Loop over the values.", "for value in values:"),
        ("Sort the values in ascending order.", "ordered = sorted(values)"),
        ("This list comprehension creates a string for each severity.", "parts = [f(n) for n in names]"),
        ("This joins all the parts together and adds the suffix.", "return ', '.join(parts) + suffix"),
        ("The condition `x > width` checks whether the word is too wide.", "if x > width:"),
        ("If the input is below 2, it returns the input directly.", "return n"),
        ("Otherwise, it calls itself twice and adds the results.", "return f(n - 1) + f(n - 2)"),
        ("It sums the values and divides by their count.", "return sum(v) / len(v)"),
        ("For each severity level, it checks for a count above zero.", "return None"),
        ("word " * 40, "x = 1"),
    ],
)
def test_comments_that_describe_or_repeat_the_code_are_dropped(text, statement):
    assert comment_problem(text, statement)


@pytest.mark.parametrize(
    ("text", "statement"),
    [
        ("Keep the last error so it can be re-raised after the final attempt.", "last_error = error"),
        ("The median needs ordered values, so sort a copy first.", "ordered = sorted(values)"),
        ("Back off exponentially so a struggling server gets time to recover.", "time.sleep(delay * (2 ** attempt))"),
        ("Windows start at 1; a zero window would divide by nothing.", "if window < 1:\n    raise ValueError('bad')"),
        ("This avoids a second pass over the list.", "total = running"),
        ("This is needed because the server returns None on a timeout.", "if reply is None:"),
        ("The cache is cleared first so a stale entry is never served.", "cache.clear()"),
        ("Since the length is odd, the median is the middle element.", "if len(ordered) % 2:"),
    ],
)
def test_comments_that_give_a_reason_are_kept(text, statement):
    assert comment_problem(text, statement) is None


def test_a_dropped_comment_is_reported_as_style_and_does_not_use_up_the_limit():
    reply = (
        "COMMENTS:\nS1: This checks if the value is unset.\nS2: Loop over the attempts.\n"
        "S4: Return func result.\n"
        "S5: Keep the last error so it can be raised once the attempts run out."
    )
    result = clio.comment_source(RETRY, FakeBackend([reply]), "comments")
    by_name = {o.name: o for o in result.outcomes}
    assert (by_name["retry S1"].status, by_name["retry S1"].cause) == ("rejected", "style")
    assert by_name["retry S2"].cause == "style"
    assert by_name["retry S4"].cause == "style"
    assert by_name["retry S5"].status == "added"
    assert "# Keep the last error" in result.text and "This checks" not in result.text
