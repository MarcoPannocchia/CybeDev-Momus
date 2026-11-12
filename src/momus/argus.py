"""Argus, the AST guard: decides whether two texts contain the same code.

Momus promises to touch only comments and docstrings. Argus is what enforces
that promise: it compares the code before and after, ignoring comments and
docstrings, and rejects everything it cannot prove unchanged (it fails
closed).

What this comparison does NOT see: spacing, quote style, redundant
parentheses and line wrapping all parse to the same tree, so a reformatted
file passes here. A second, byte-level check covers that (plan §7).
"""

import ast
from dataclasses import dataclass

# The node types that can carry a docstring, as Python itself defines it.
_DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


class ArgusError(Exception):
    """Raised when source text cannot be analysed, whatever the reason."""


@dataclass(frozen=True)
class Verdict:
    """The guard's answer: whether the code is unchanged, and why."""

    accepted: bool
    reason: str


def _is_docstring(statement: ast.stmt) -> bool:
    """Tell whether ``statement``, the first of a body, is a docstring.

    This mirrors Python's own rule: a bare expression statement holding a
    plain string constant. F-strings, bytes and any other string-like
    expression are code and must stay visible to the comparison.
    """
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def normalized_tree(source: str) -> ast.Module:
    """Parse ``source`` and remove its docstrings, leaving only the code.

    This is the one place where source is normalized; anything that needs to
    reason about "the code without its documentation" should call it rather
    than repeat the rules.

    Raises:
        ArgusError: if ``source`` is not text or cannot be parsed.
    """
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


def code_fingerprint(source: str) -> str:
    """Return a string that is equal for two texts exactly when their code is.

    It is the dump of the normalized tree without line or column positions, so
    it does not move when comments or docstrings are added above the code.

    Raises:
        ArgusError: if ``source`` cannot be analysed.
    """
    tree = normalized_tree(source)
    try:
        return ast.dump(tree, include_attributes=False)
    except Exception as exc:
        # `ast.dump` recurses and can overflow on very deeply nested code.
        raise ArgusError(f"cannot dump: {type(exc).__name__}: {exc}") from exc


def compare_code(original: str, new: str) -> Verdict:
    """Decide whether ``new`` has the same code as ``original``.

    Only comments and docstrings may differ. Any doubt is a rejection: if
    either text cannot be analysed, the verdict is negative. An unparseable
    original is rejected too, because nothing can then be proven about the
    new text. This function never raises.
    """
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
