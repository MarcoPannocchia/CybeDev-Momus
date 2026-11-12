"""Tests for the file splitter (plan §8)."""

import ast
import textwrap

import pytest

from momus.splitter import Piece, SplitError, join_pieces, split_source

SAMPLE = textwrap.dedent(
    '''
    """Small helpers used only by the tests."""
    import functools

    LIMIT = 3


    # Decorator defined first so it can be used below.
    def logged(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper


    @logged
    @functools.lru_cache(
        maxsize=None,
    )
    def square(n):
        return n * n


    async def fetch(n):
        return n


    class Counter:
        """Counts upwards."""

        step = 1

        def __init__(self):
            self.value = 0

        @property
        def doubled(self):
            return self.value * 2

        # A comment between methods.
        async def tick(self):
            self.value += self.step


    if __name__ == "__main__":
        print(square(LIMIT))
    # trailing comment
    '''
).lstrip("\n")


def summary(pieces: list[Piece]) -> list[tuple[str, str | None]]:
    return [(piece.kind, piece.name) for piece in pieces]


def by_name(pieces: list[Piece], name: str) -> Piece:
    (piece,) = [piece for piece in pieces if piece.name == name and piece.kind != "class-part"]
    return piece


def test_file_is_split_into_functions_classes_and_the_rest():
    assert summary(split_source(SAMPLE)) == [
        ("other", None),
        ("function", "logged"),
        ("other", None),
        ("function", "square"),
        ("other", None),
        ("function", "fetch"),
        ("other", None),
        ("class", "Counter"),
        ("other", None),
    ]


def test_decorators_belong_to_the_piece_they_decorate():
    square = by_name(split_source(SAMPLE), "square")
    assert square.text.startswith("@logged\n@functools.lru_cache(\n")
    assert square.text.endswith("    return n * n\n")


def test_nested_function_stays_inside_its_parent():
    logged = by_name(split_source(SAMPLE), "logged")
    assert "def wrapper" in logged.text
    assert logged.text.endswith("    return wrapper\n")


def test_line_numbers_match_the_text():
    lines = SAMPLE.splitlines(keepends=True)
    for piece in split_source(SAMPLE):
        assert piece.text == "".join(lines[piece.start_line - 1 : piece.end_line])


def test_each_function_and_class_piece_parses_on_its_own():
    for piece in split_source(SAMPLE):
        if piece.kind in ("function", "class"):
            ast.parse(piece.text)


@pytest.mark.parametrize(
    "source",
    [
        SAMPLE,
        SAMPLE.replace("\n", "\r\n"),  # Windows line endings
        SAMPLE.rstrip("\n"),  # no final newline
        "def only():\n    return 1",  # one function, no final newline
        "# just a comment\n\nx = 1\n",  # nothing to split off
        "",  # empty file
        "\n\n\n",  # blank lines only
        "def a(): return 1\ndef b(): return 2\n",  # adjacent one-liners
        "x = 1\x0c\ndef f():\n    return x\n",  # form feed is not a line break
    ],
)
@pytest.mark.parametrize("max_class_lines", [None, 0])
def test_reassembled_pieces_reproduce_the_file_exactly(source, max_class_lines):
    pieces = split_source(source, max_class_lines=max_class_lines)
    assert join_pieces(pieces) == source
    assert join_pieces(pieces).encode("utf-8") == source.encode("utf-8")
    # Pieces follow each other with no gap and no overlap.
    expected_start = 1
    for piece in pieces:
        assert piece.start_line == expected_start
        expected_start = piece.end_line + 1


def test_large_class_is_split_per_method():
    pieces = split_source(SAMPLE, max_class_lines=5)
    counter = [p for p in pieces if p.name and p.name.startswith("Counter")]
    assert summary(counter) == [
        ("class-part", "Counter"),
        ("method", "Counter.__init__"),
        ("class-part", "Counter"),
        ("method", "Counter.doubled"),
        ("class-part", "Counter"),
        ("method", "Counter.tick"),
    ]
    assert counter[0].text.startswith("class Counter:\n")
    assert "step = 1" in counter[0].text
    doubled = by_name(pieces, "Counter.doubled")
    assert doubled.text == "    @property\n    def doubled(self):\n        return self.value * 2\n"


def test_class_within_the_limit_is_kept_whole():
    assert ("class", "Counter") in summary(split_source(SAMPLE, max_class_lines=500))


@pytest.mark.parametrize("bad", ["def broken(:\n    pass\n", None, b"x = 1\n", "x = 1\n\x00"])
def test_file_that_cannot_be_parsed_is_refused(bad):
    with pytest.raises(SplitError):
        split_source(bad)
