# Argus, the AST guard: decides whether two texts contain the same code.
#
# Momus promises to touch only comments and docstrings. Argus is what enforces
# that promise: it compares the code before and after, ignoring comments and
# docstrings, and rejects everything it cannot prove unchanged (it fails
# closed).
#
# What the tree comparison does NOT see: spacing, quote style, redundant
# parentheses and line wrapping all parse to the same tree, so a reformatted
# file passes it. The second check, `check_inserted_lines`, covers that: the
# lines Momus added, once removed, must give back the original text exactly.

import ast
import re
from collections.abc import Iterable
from dataclasses import dataclass

# The node types that can carry a docstring, as Python itself defines it.
_DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


# Raised when source text cannot be analysed, whatever the reason.
class ArgusError(Exception):
    pass


# The guard's answer: whether the code is unchanged, and why.
@dataclass(frozen=True)
class Verdict:
    accepted: bool
    reason: str


# Tell whether `statement`, the first of a body, is a docstring.
#
# This mirrors Python's own rule: a bare expression statement holding a
# plain string constant. F-strings, bytes and any other string-like
# expression are code and must stay visible to the comparison.
def _is_docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


# Parse `source` and remove its docstrings, leaving only the code.
#
# This is the one place where source is normalized; anything that needs to
# reason about "the code without its documentation" should call it rather
# than repeat the rules.
#
# Raises:
#     ArgusError: if `source` is not text or cannot be parsed.
def normalized_tree(source: str) -> ast.Module:
    if not isinstance(source, str):
        raise ArgusError(f"source must be text, got {type(source).__name__}")
    try:
        tree = ast.parse(source)
    except Exception as exc:
        # Deliberately broad: besides SyntaxError, the parser can raise
        # ValueError (null bytes), RecursionError or MemoryError. For a guard,
        # every one of them means the same thing: not provably safe.
        raise ArgusError(f"cannot parse: {type(exc).__name__}: {exc}") from exc

    # Collected first, because bodies are edited while the tree is traversed.
    owners = [node for node in ast.walk(tree) if isinstance(node, _DOCSTRING_OWNERS)]
    for owner in owners:
        if owner.body and _is_docstring(owner.body[0]):
            del owner.body[0]
        # A function or class may not have an empty body. `pass` is what such
        # a body means, so a docstring-only body and a `pass`-only body
        # compare equal. A module may be empty and is left as it is.
        if not owner.body and not isinstance(owner, ast.Module):
            owner.body.append(ast.Pass())
    return tree


# Return a string that is equal for two texts exactly when their code is.
#
# It is the dump of the normalized tree without line or column positions, so
# it does not move when comments or docstrings are added above the code.
#
# Raises:
#     ArgusError: if `source` cannot be analysed.
def code_fingerprint(source: str) -> str:
    tree = normalized_tree(source)
    try:
        return ast.dump(tree, include_attributes=False)
    except Exception as exc:
        # `ast.dump` recurses and can overflow on very deeply nested code.
        raise ArgusError(f"cannot dump: {type(exc).__name__}: {exc}") from exc


# Decide whether `new` has the same code as `original`.
#
# Only comments and docstrings may differ. Any doubt is a rejection: if
# either text cannot be analysed, the verdict is negative. An unparseable
# original is rejected too, because nothing can then be proven about the
# new text. This function never raises.
def compare_code(original: str, new: str) -> Verdict:
    try:
        before = code_fingerprint(original)
    except ArgusError as exc:
        return Verdict(False, f"original rejected: {exc}")
    try:
        after = code_fingerprint(new)
    except ArgusError as exc:
        return Verdict(False, f"new code rejected: {exc}")
    if before != after:
        return Verdict(False, "code differs from the original")
    return Verdict(True, "code identical apart from comments and docstrings")


# One line of text with its own ending kept. Only the endings Python itself
# counts as a new source line are used (\n, \r\n, \r). `str.splitlines`
# would also split on form feeds and Unicode separators, and the line numbers
# would then disagree with the ones `ast` reports.
_LINE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+")
_ENDING = re.compile(r"\r\n|\r|\n")


# Split `text` into lines that, joined back, give `text` exactly.
def split_lines(text: str) -> list[str]:
    return _LINE.findall(text)


# Decide whether `new` is `original` plus exactly the inserted lines.
#
# `inserted_lines` holds the 1-based numbers, in `new`, of the lines
# Momus added. Removing those lines must give `original` character for
# character, so every other line is untouched: no reformatting, no changed
# spacing, no altered line ending. Characters are compared, which is the
# same as comparing bytes for any single encoding.
#
# Rejected, because none of them can be proven safe: input that is not
# text, line numbers that are not whole numbers, are repeated or fall
# outside `new`, an empty set when the texts differ, and a mix of line
# ending styles in either text. This function never raises.
def check_inserted_lines(original: str, new: str, inserted_lines: Iterable[int]) -> Verdict:
    if not isinstance(original, str) or not isinstance(new, str):
        return Verdict(False, "both texts must be text")
    try:
        numbers = list(inserted_lines)
    except TypeError:
        return Verdict(False, "inserted lines must be a collection of line numbers")
    # `bool` is a kind of `int` in Python; True would silently mean line 1.
    if any(not isinstance(n, int) or isinstance(n, bool) for n in numbers):
        return Verdict(False, "line numbers must be whole numbers")
    if len(set(numbers)) != len(numbers):
        return Verdict(False, "a line number is repeated")

    # Checked on both texts together, so an inserted line that ends
    # differently from the file is caught as well as a file that was already
    # inconsistent.
    endings = set(_ENDING.findall(original)) | set(_ENDING.findall(new))
    if len(endings) > 1:
        return Verdict(False, "mixed line endings")

    new_lines = split_lines(new)
    if any(n < 1 or n > len(new_lines) for n in numbers):
        return Verdict(False, "a line number is outside the new text")
    if not numbers and original != new:
        return Verdict(False, "no inserted lines were given, but the texts differ")

    removed = set(numbers)
    remainder = "".join(
        line for number, line in enumerate(new_lines, start=1) if number not in removed
    )
    if remainder != original:
        return Verdict(False, "removing the inserted lines does not give the original text")
    return Verdict(True, "the original text is intact around the inserted lines")
