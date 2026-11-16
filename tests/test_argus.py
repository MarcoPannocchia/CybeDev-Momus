"""Tests for Argus, the AST guard (plan §7).

Every sample is a small neutral function written for the purpose. "Accepted"
means the guard found the code unchanged; "discarded" means it rejected the
new text.
"""

import io
import subprocess
import textwrap

import pytest

from momus.argus import (
    ArgusError,
    Verdict,
    check_inserted_lines,
    code_fingerprint,
    compare_code,
    normalized_tree,
)
from momus.cli import guard_command, main
from momus.critic import CriticError


def src(text: str) -> str:
    """Dedent a triple-quoted sample so tests can be indented naturally."""
    return textwrap.dedent(text).lstrip("\n")


ORIGINAL = src(
    """
    def add(a, b):
        total = a + b
        return total
    """
)


def accepted(original: str, new: str) -> bool:
    verdict = compare_code(original, new)
    assert isinstance(verdict, Verdict)
    assert verdict.reason
    return verdict.accepted


# --- Tests listed in the plan ---------------------------------------------


def test_same_code_with_docstring_added_is_accepted():
    new = src(
        '''
        def add(a, b):
            """Return the sum of a and b."""
            total = a + b
            return total
        '''
    )
    assert accepted(ORIGINAL, new)


def test_renamed_variable_is_discarded():
    new = src(
        """
        def add(a, b):
            result = a + b
            return result
        """
    )
    assert not accepted(ORIGINAL, new)


def test_line_of_code_added_is_discarded():
    new = src(
        """
        def add(a, b):
            total = a + b
            print(total)
            return total
        """
    )
    assert not accepted(ORIGINAL, new)


def test_line_of_code_removed_is_discarded():
    new = src(
        """
        def add(a, b):
            return total
        """
    )
    assert not accepted(ORIGINAL, new)


def test_string_literal_changed_is_discarded():
    original = 'def greet():\n    return "hello"\n'
    new = 'def greet():\n    return "hullo"\n'
    assert not accepted(original, new)


@pytest.mark.parametrize(
    "new",
    [
        "def add(a, b)\n    return a + b\n",  # missing colon
        "Here is the commented code:\n\ndef add(a, b):\n    return a + b\n",  # chatter
        "```python\ndef add(a, b):\n    return a + b\n```\n",  # markdown fence
        "def add(a, b):\nreturn a + b\n",  # broken indentation
        "",  # nothing at all
    ],
)
def test_invalid_output_is_discarded(new):
    assert not accepted(ORIGINAL, new)


def test_same_code_with_hash_comments_added_is_accepted():
    new = src(
        """
        # Small arithmetic helper.
        def add(a, b):
            # Keep the sum in a name so it is easy to inspect.
            total = a + b  # inline note
            return total
        """
    )
    assert accepted(ORIGINAL, new)


def test_tuple_changed_to_parenthesised_value_is_discarded():
    assert not accepted("x = (1,)\n", "x = (1)\n")


# --- Edge case: a body that is only a docstring ----------------------------


@pytest.mark.parametrize(
    "header",
    ["def stub():", "async def stub():", "class Stub:"],
)
def test_docstring_only_body_is_normalized_to_pass(header):
    with_doc = f'{header}\n    """Explain the stub."""\n'
    other_doc = f'{header}\n    """A different explanation."""\n'
    with_pass = f"{header}\n    pass\n"
    assert accepted(with_doc, other_doc)
    assert accepted(with_pass, with_doc)
    assert accepted(with_doc, with_pass)


def test_docstring_only_body_differs_from_a_body_with_code():
    assert not accepted('def stub():\n    """Doc."""\n', "def stub():\n    return 1\n")


# --- Docstrings are ignored wherever Python allows one ---------------------


def test_docstrings_added_at_every_level_are_accepted():
    original = src(
        """
        import math

        class Circle:
            def area(self, radius):
                return math.pi * radius ** 2

            async def describe(self):
                def helper():
                    return "circle"
                return helper()
        """
    )
    new = src(
        '''
        """Geometry helpers."""
        import math

        class Circle:
            """A circle."""

            def area(self, radius):
                """Return the area."""
                return math.pi * radius ** 2

            async def describe(self):
                """Return the shape name."""
                def helper():
                    """Name of the shape."""
                    return "circle"
                return helper()
        '''
    )
    assert accepted(original, new)


def test_existing_docstring_reworded_is_accepted():
    # Argus does not enforce ownership (plan §7): that is Clio's job.
    original = 'def f():\n    """Old."""\n    return 1\n'
    new = 'def f():\n    """New wording."""\n    return 1\n'
    assert accepted(original, new)


# --- Edge case: ordinary strings are code, never ignored -------------------


def test_string_statement_that_is_not_first_is_not_ignored():
    original = 'def f():\n    x = 1\n    "note"\n    return x\n'
    changed = 'def f():\n    x = 1\n    "other note"\n    return x\n'
    assert not accepted(original, changed)


def test_string_statement_added_after_code_is_discarded():
    original = "def f():\n    x = 1\n    return x\n"
    new = 'def f():\n    x = 1\n    "this looks like documentation"\n    return x\n'
    assert not accepted(original, new)


def test_second_string_after_docstring_is_not_ignored():
    original = 'def f():\n    """Doc."""\n    return 1\n'
    new = 'def f():\n    """Doc."""\n    """Extra."""\n    return 1\n'
    assert not accepted(original, new)


def test_string_in_a_default_argument_is_not_ignored():
    assert not accepted('def f(mode="r"):\n    pass\n', 'def f(mode="w"):\n    pass\n')


# --- Edge case: string-like expressions are never treated as docstrings ----


@pytest.mark.parametrize(
    ("original", "new"),
    [
        ('def f(n):\n    f"count {n}"\n', 'def f(n):\n    f"total {n}"\n'),  # f-string
        ('def f():\n    b"raw"\n', 'def f():\n    b"new"\n'),  # bytes
        ('def f(n):\n    "count " + n\n', 'def f(n):\n    "total " + n\n'),  # expression
        ('def f(n):\n    f"count {n}"\n', "def f(n):\n    pass\n"),  # f-string removed
    ],
)
def test_string_like_first_statements_are_not_ignored(original, new):
    assert not accepted(original, new)


def test_fstring_changed_inside_code_is_discarded():
    assert not accepted('x = 1\ny = f"{x} items"\n', 'x = 1\ny = f"{x} things"\n')


# --- Fail closed -----------------------------------------------------------


def test_unparseable_original_is_discarded_even_if_texts_are_equal():
    broken = "def add(a, b)\n    return a + b\n"
    assert not accepted(broken, broken)


@pytest.mark.parametrize("bad", [None, b"x = 1\n", 42])
def test_non_text_input_is_discarded(bad):
    assert not accepted("x = 1\n", bad)
    assert not accepted(bad, "x = 1\n")


def test_null_byte_is_discarded():
    assert not accepted("x = 1\n", "x = 1\n\x00")


@pytest.mark.parametrize("depth", [100_000, 5_000])
def test_code_too_deep_to_analyse_is_discarded_without_crashing(depth):
    # Equal on both sides on purpose, to show that "cannot analyse" is a
    # rejection even when nothing changed. On CPython 3.12 the larger depth
    # overflows the parser and the smaller one parses but overflows the dump.
    deep = "x = " + "-" * depth + "1\n"
    assert not accepted(deep, deep)


# --- The reusable normalization (plan §7 design note) ----------------------


def test_fingerprint_ignores_comments_docstrings_and_position():
    plain = "def f():\n    return 1\n"
    documented = '# top\n\n\ndef f():\n    """Doc."""\n    return 1  # one\n'
    assert code_fingerprint(plain) == code_fingerprint(documented)
    assert code_fingerprint(plain) != code_fingerprint("def f():\n    return 2\n")


def test_normalization_raises_argus_error_on_bad_source():
    with pytest.raises(ArgusError):
        normalized_tree("def (:\n")
    with pytest.raises(ArgusError):
        code_fingerprint(None)


# --- Second check: the original text is intact around inserted lines -------

BEFORE = "def add(a, b):\n    return a + b\n"
AFTER = 'def add(a, b):\n    """Return the sum."""\n    # plain addition\n    return a + b\n'


def intact(original, new, inserted) -> bool:
    verdict = check_inserted_lines(original, new, inserted)
    assert isinstance(verdict, Verdict)
    assert verdict.reason
    return verdict.accepted


def test_inserted_lines_removed_give_original_is_accepted():
    assert intact(BEFORE, AFTER, [2, 3])
    assert intact(BEFORE, AFTER, {3, 2})  # any collection, any order


def test_no_insertions_and_equal_texts_is_accepted():
    assert intact(BEFORE, BEFORE, [])


def test_empty_set_when_texts_differ_is_discarded():
    assert not intact(BEFORE, AFTER, [])


@pytest.mark.parametrize("inserted", [[0, 2], [-1], [2, 5], [99]])
def test_line_numbers_out_of_range_are_discarded(inserted):
    assert not intact(BEFORE, AFTER, inserted)


def test_duplicate_line_numbers_are_discarded():
    assert not intact(BEFORE, AFTER, [2, 3, 3])


@pytest.mark.parametrize("inserted", [[2], [2, 3, 4], [1, 2]])
def test_wrong_set_of_lines_is_discarded(inserted):
    assert not intact(BEFORE, AFTER, inserted)


def test_reformatted_code_line_is_discarded():
    # The tree comparison accepts this; the byte check is what rejects it.
    reformatted = 'def add(a, b):\n    """Return the sum."""\n    return a+b\n'
    assert compare_code(BEFORE, reformatted).accepted
    assert not intact(BEFORE, reformatted, [2])


def test_trailing_whitespace_added_to_a_code_line_is_discarded():
    new = 'def add(a, b):  \n    """Return the sum."""\n    return a + b\n'
    assert not intact(BEFORE, new, [2])


def test_pass_replaced_by_docstring_is_discarded():
    # Accepted by the tree comparison (plan §7); stopped here.
    original = "def stub():\n    pass\n"
    new = 'def stub():\n    """Explain the stub."""\n'
    assert compare_code(original, new).accepted
    assert not intact(original, new, [2])


# Line endings


def test_consistent_crlf_text_is_accepted():
    original = "def add(a, b):\r\n    return a + b\r\n"
    new = "def add(a, b):\r\n    # plain addition\r\n    return a + b\r\n"
    assert intact(original, new, [2])


def test_inserted_line_with_a_different_ending_is_discarded():
    original = "def add(a, b):\r\n    return a + b\r\n"
    new = "def add(a, b):\r\n    # plain addition\n    return a + b\r\n"
    assert not intact(original, new, [2])


def test_line_endings_converted_in_the_new_text_are_discarded():
    original = "def add(a, b):\r\n    return a + b\r\n"
    new = "def add(a, b):\n    # plain addition\n    return a + b\n"
    assert not intact(original, new, [2])


def test_original_with_mixed_line_endings_is_discarded_even_if_unchanged():
    mixed = "x = 1\r\ny = 2\n"
    assert not intact(mixed, mixed, [])


def test_form_feed_is_not_counted_as_a_line_break():
    # Python does not start a new source line at a form feed, so the inserted
    # comment is line 2, not line 3.
    original = "x = 1\x0c\ny = 2\n"
    new = "x = 1\x0c\n# note\ny = 2\n"
    assert intact(original, new, [2])
    assert not intact(original, new, [3])


# Final newline


def test_original_without_final_newline_stays_without_it():
    original = "x = 1\ny = 2"
    assert intact(original, "x = 1\n# note\ny = 2", [2])


def test_final_newline_added_to_the_original_last_line_is_discarded():
    # Appending a comment after the last line forces a newline onto `y = 2`,
    # which changes a byte of the original.
    original = "x = 1\ny = 2"
    assert not intact(original, "x = 1\ny = 2\n# note", [3])
    assert not intact(original, "x = 1\ny = 2\n# note\n", [3])


def test_final_newline_removed_from_the_original_is_discarded():
    assert not intact("x = 1\ny = 2\n", "x = 1\n# note\ny = 2", [2])


def test_inserted_last_line_without_newline_leaves_original_bytes_intact():
    assert intact("x = 1\n", "x = 1\n# note", [2])


# Fail closed on bad input


@pytest.mark.parametrize("bad", [None, b"x = 1\n", 7])
def test_inserted_check_rejects_non_text(bad):
    assert not intact(bad, AFTER, [2, 3])
    assert not intact(BEFORE, bad, [2, 3])


@pytest.mark.parametrize("inserted", [None, 2, [2.0, 3], ["2", "3"], [True, 3]])
def test_inserted_check_rejects_bad_line_numbers(inserted):
    assert not intact(BEFORE, AFTER, inserted)


# --- The command: `momus guard` --------------------------------------------

WITH_COMMENTS = src(
    '''
    def add(a, b):
        """Return the sum of a and b."""
        # Kept in a variable so a debugger can show it.
        total = a + b
        return total
    '''
)


def run_guard(tmp_path, text, baseline=ORIGINAL):
    path = tmp_path / "m.py"
    path.write_text(text)
    out = io.StringIO()
    status = guard_command([path], read_baseline=lambda p, ref: baseline, out=out)
    assert path.read_text() == text  # the guard never edits the file
    return status, out.getvalue(), path


def test_guard_accepts_added_comments_and_counts_them(tmp_path):
    status, out, path = run_guard(tmp_path, WITH_COMMENTS)
    assert (status, out) == (0, f"{path}: ok - 1 docstring(s) and 1 comment(s) added\n")


def test_guard_accepts_an_unchanged_file(tmp_path):
    status, out, _ = run_guard(tmp_path, ORIGINAL)
    assert status == 0 and "ok - 0 docstring(s) and 0 comment(s) added" in out


@pytest.mark.parametrize(
    "text",
    [
        WITH_COMMENTS.replace("a + b", "a - b"),  # code changed
        ORIGINAL.replace("a + b", "a+b"),  # reformatted: same tree, other bytes
        ORIGINAL + "print(add(1, 2))\n",  # code added
        "def add(a, b:\n",  # does not parse
    ],
)
def test_guard_rejects_anything_but_added_comments(tmp_path, text):
    status, out, path = run_guard(tmp_path, text)
    assert status == 1 and out.startswith(f"{path}: REJECTED - ")


def test_guard_rejects_an_existing_comment_that_was_edited(tmp_path):
    edited = WITH_COMMENTS.replace("debugger", "person")
    status, out, _ = run_guard(tmp_path, edited, baseline=WITH_COMMENTS)
    assert status == 1 and "REJECTED - same code, but" in out


def test_guard_code_only_accepts_what_leaves_the_code_identical(tmp_path):
    for text, baseline in [
        (WITH_COMMENTS.replace("debugger", "person"), WITH_COMMENTS),  # comment edited
        (ORIGINAL, WITH_COMMENTS),  # comments removed
        (ORIGINAL.replace("a + b", "a+b"), ORIGINAL),  # reformatted
    ]:
        path = tmp_path / "m.py"
        path.write_text(text)
        out = io.StringIO()
        assert guard_command([path], read_baseline=lambda p, ref: baseline, out=out) == 1
        assert guard_command([path], read_baseline=lambda p, ref: baseline, out=out, code_only=True) == 0
    assert out.getvalue().endswith("ok - code identical apart from comments and docstrings\n")


def test_guard_code_only_still_rejects_a_code_change(tmp_path):
    path = tmp_path / "m.py"
    path.write_text(WITH_COMMENTS.replace("a + b", "a - b"))
    out = io.StringIO()
    assert guard_command([path], read_baseline=lambda p, ref: ORIGINAL, out=out, code_only=True) == 1
    assert "REJECTED - code differs from the original" in out.getvalue()
    assert main(["guard", str(path), "--code-only"]) == 1  # no baseline: still a failure


def test_guard_fails_when_a_file_cannot_be_checked(tmp_path, capsys):
    def no_baseline(path, ref):
        raise CriticError("no baseline at HEAD")

    path = tmp_path / "m.py"
    path.write_text(WITH_COMMENTS)
    assert guard_command([path], read_baseline=no_baseline) == 1
    assert guard_command([tmp_path / "missing.py"], read_baseline=lambda p, ref: ORIGINAL) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.count("cannot check") == 2


def test_guard_checks_every_file_and_fails_if_one_does(tmp_path):
    good, bad = tmp_path / "good.py", tmp_path / "bad.py"
    good.write_text(WITH_COMMENTS)
    bad.write_text(ORIGINAL.replace("a + b", "a * b"))
    out = io.StringIO()
    assert guard_command([bad, good], read_baseline=lambda p, ref: ORIGINAL, out=out) == 1
    assert out.getvalue().splitlines() == [
        f"{bad}: REJECTED - code differs from the original",
        f"{good}: ok - 1 docstring(s) and 1 comment(s) added",
    ]


def test_guard_runs_from_the_command_line_against_git(tmp_path, capsys):
    def git(*args):
        subprocess.run(
            ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
            check=True,
            capture_output=True,
        )

    path = tmp_path / "m.py"
    path.write_text(ORIGINAL)
    git("init", "-q")
    git("add", "m.py")
    git("commit", "-q", "-m", "x")
    path.write_text(WITH_COMMENTS)
    assert main(["guard", str(path)]) == 0
    assert "1 docstring(s) and 1 comment(s) added" in capsys.readouterr().out
    git("commit", "-q", "-a", "-m", "y")
    assert main(["guard", str(path)]) == 0
    assert "0 docstring(s) and 0 comment(s) added" in capsys.readouterr().out
    assert main(["guard", str(path), "--base", "HEAD~1"]) == 0
    assert "1 docstring(s) and 1 comment(s) added" in capsys.readouterr().out
    path.write_text(WITH_COMMENTS.replace("return total", "return a"))
    assert main(["guard", str(path)]) == 1
    assert "REJECTED" in capsys.readouterr().out
