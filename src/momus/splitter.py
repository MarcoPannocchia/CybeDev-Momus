# Splits a Python file into small pieces, one per function or class.
#
# A local model on a CPU is slow and has a small context, so each request must
# stay small. The splitter cuts a file into pieces that cover every line of it:
# functions and classes become their own pieces, and whatever lies between them
# (imports, constants, comments, blank lines) becomes "other" pieces. Glued back
# together in order, the pieces give the original file exactly.

import ast
from dataclasses import dataclass

from momus.argus import split_lines

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


# Raised when a file cannot be split safely.
class SplitError(Exception):
    pass


# A run of consecutive lines of a file.
#
# `kind` is `"function"`, `"class"`, `"method"`, `"class-part"`
# (the lines of a split class that are not a method) or `"other"`.
# `name` is the qualified name (`"Circle.area"` for a method, the class
# name for a class-part) and `None` for `"other"`. Line numbers are
# 1-based and inclusive, as in `ast`.
@dataclass(frozen=True)
class Piece:
    kind: str
    name: str | None
    start_line: int
    end_line: int
    text: str


# Return the line where `node` starts, counting its decorators.
#
# `ast` reports the line of the `def` or `class` keyword; a decorator
# sits above it and belongs to the same piece.
def _first_line(node: ast.stmt) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *(decorator.lineno for decorator in decorators)])


# Cut one class into its methods and the lines around them.
def _class_ranges(node: ast.ClassDef) -> list[tuple[str, str, int, int]]:
    ranges = []
    cursor = _first_line(node)
    for child in node.body:
        if not isinstance(child, _FUNCTIONS):
            continue
        start = _first_line(child)
        if start > cursor:
            ranges.append(("class-part", node.name, cursor, start - 1))
        ranges.append(("method", f"{node.name}.{child.name}", start, child.end_lineno))
        cursor = child.end_lineno + 1
    if cursor <= node.end_lineno:
        ranges.append(("class-part", node.name, cursor, node.end_lineno))
    return ranges


# Split `source` into pieces that cover every line, in order.
#
# Top-level functions and classes become one piece each. With
# `max_class_lines` set, a class longer than that many lines is cut
# further into one piece per method plus the lines around them. Nested
# functions and classes are never split off.
#
# Raises:
#     SplitError: if `source` is not text, cannot be parsed, or the
#         pieces would not rebuild it exactly.
def split_source(source: str, max_class_lines: int | None = None) -> list[Piece]:
    if not isinstance(source, str):
        raise SplitError(f"source must be text, got {type(source).__name__}")
    try:
        tree = ast.parse(source)
    except Exception as exc:
        # Same reasoning as in Argus: whatever the parser's complaint is, a
        # file that cannot be parsed cannot be split by its structure.
        raise SplitError(f"cannot parse: {type(exc).__name__}: {exc}") from exc

    ranges: list[tuple[str, str | None, int, int]] = []
    for node in tree.body:
        if isinstance(node, _FUNCTIONS):
            ranges.append(("function", node.name, _first_line(node), node.end_lineno))
        elif isinstance(node, ast.ClassDef):
            start, end = _first_line(node), node.end_lineno
            if max_class_lines is not None and end - start + 1 > max_class_lines:
                ranges.extend(_class_ranges(node))
            else:
                ranges.append(("class", node.name, start, end))

    lines = split_lines(source)
    pieces: list[Piece] = []

    def add(kind: str, name: str | None, start: int, end: int) -> None:
        pieces.append(Piece(kind, name, start, end, "".join(lines[start - 1 : end])))

    cursor = 1
    for kind, name, start, end in ranges:
        if start < cursor or end < start or end > len(lines):
            raise SplitError(f"unexpected line range for {name}: {start}-{end}")
        if start > cursor:
            add("other", None, cursor, start - 1)
        add(kind, name, start, end)
        cursor = end + 1
    if cursor <= len(lines):
        add("other", None, cursor, len(lines))

    # The promise of this module, checked on every call rather than assumed.
    if join_pieces(pieces) != source:
        raise SplitError("pieces do not rebuild the original text")
    return pieces


# Glue `pieces` back together in the order given.
def join_pieces(pieces: list[Piece]) -> str:
    return "".join(piece.text for piece in pieces)
