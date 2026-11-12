"""Tests for Argus, the AST guard (plan §7).

Every sample is a small neutral function written for the purpose. "Accepted"
means the guard found the code unchanged; "discarded" means it rejected the
new text.
"""

import textwrap

import pytest

from momus.argus import ArgusError, Verdict, code_fingerprint, compare_code, normalized_tree


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
