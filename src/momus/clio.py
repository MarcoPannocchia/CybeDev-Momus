"""Clio, the commenting stage: adds missing docstrings with a model.

The model only ever returns the text of a docstring. Momus finds the right
place with ``ast`` line numbers and inserts the docstring itself, so the model
never has the chance to touch the code. Every insertion is then checked twice
by Argus (the code is identical, and removing the inserted lines gives back
the original text exactly), and anything that fails is dropped.

Nothing here writes to a file except ``write_text_atomic``, which callers use
only after the checks have passed.
"""

import ast
import os
import re
import shutil
import tempfile
import textwrap
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from momus import argus
from momus.backends import Backend, BackendError
from momus.cleaning import clean_output, strip_reasoning
from momus.splitter import SplitError, split_source

ADDED = "added"
SKIPPED = "skipped"
REJECTED = "rejected"

_MARKER = re.compile(r"\A\s*DOCSTRING:[ \t]*", re.IGNORECASE)
# Where a model starts repeating the code after its answer: a "Code:" label or
# a fence. The docstring ends there.
_ECHO = re.compile(r"^(?:[ \t]*```|Code:)", re.MULTILINE)
_ENDING = re.compile(r"\r\n|\r|\n")
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


class ClioError(Exception):
    """Raised for a model reply that cannot be turned into a docstring."""


@dataclass(frozen=True)
class Outcome:
    """What happened to one function, method or class."""

    name: str
    status: str  # ADDED, SKIPPED (left alone on purpose) or REJECTED (a check failed)
    reason: str


@dataclass(frozen=True)
class ClioResult:
    """The new text of a file and the outcome for each target in it.

    ``text`` equals the original text when nothing was added. Line numbers in
    ``inserted_lines`` are 1-based and refer to ``text``.
    """

    text: str
    outcomes: tuple[Outcome, ...]
    inserted_lines: tuple[int, ...]

    @property
    def changed(self) -> bool:
        return bool(self.inserted_lines)


@dataclass(frozen=True)
class _Target:
    name: str
    kind: str  # "function", "method" or "class"
    code: str  # source shown to the model
    context: str  # one sentence of extra information for the model, or ""
    index: int  # 0-based line of the original before which the docstring goes
    indent: str


# --- Prompt and reply ------------------------------------------------------


def load_prompt() -> str:
    """Read the prompt template; it lives in a plain file so it is easy to edit."""
    return resources.files("momus").joinpath("prompts/clio.txt").read_text(encoding="utf-8")


def build_prompt(kind: str, code: str, context: str = "") -> str:
    """Fill the template. Plain replacement, because code is full of braces."""
    prompt = load_prompt()
    for marker, value in (("{{KIND}}", kind), ("{{CONTEXT}}", context), ("{{CODE}}", code)):
        prompt = prompt.replace(marker, value)
    return prompt


def parse_reply(reply: str) -> str:
    """Extract the docstring text from a model reply.

    The reply must contain a ``DOCSTRING:`` line followed by the text. Quotes
    the model put around the text are removed, and so is any copy of the code
    the model repeated after its answer.

    Raises:
        ClioError: if the marker is missing, the text is empty, or it contains
            a triple double quote, which would end the docstring early.
    """
    text = strip_reasoning(reply)
    match = _MARKER.match(text)
    if match is None:
        # Perhaps the whole answer is inside a fence, or has a sentence before it.
        text = clean_output(text)
        match = _MARKER.match(text)
    if match is None:
        raise ClioError("reply does not start with DOCSTRING:")
    # Read the marker before looking at fences: a model often repeats the code
    # in a fence after its answer, and that fence is not the answer.
    text = _ECHO.split(text[match.end() :], maxsplit=1)[0]
    text = textwrap.dedent(text).strip()
    for quote in ('"""', "'''"):
        if text.startswith(quote) and text.endswith(quote) and len(text) >= 2 * len(quote):
            text = text[len(quote) : -len(quote)].strip()
            break
    if not text:
        raise ClioError("the docstring is empty")
    if '"""' in text:
        raise ClioError("the docstring contains a triple double quote")
    # A backslash would be read as an escape; doubling keeps the intended text.
    return text.replace("\\", "\\\\")


def format_docstring(text: str, indent: str, newline: str) -> list[str]:
    """Lay out ``text`` as the lines of a triple-quoted docstring."""
    lines = [line.rstrip() for line in text.split("\n")]
    # The closing quotes go on their own line when the text ends in a quote
    # mark, because ``"..."`"""`` would end the string in the wrong place.
    if len(lines) == 1 and not lines[0].endswith('"'):
        return [f'{indent}"""{lines[0]}"""{newline}']
    body = [f"{indent}{line}{newline}" if line else newline for line in lines[1:]]
    return [f'{indent}"""{lines[0]}{newline}', *body, f'{indent}"""{newline}']


# --- Finding where docstrings go -------------------------------------------


def _first_line(node: ast.stmt) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *(decorator.lineno for decorator in decorators)])


def _slot(node: ast.AST, lines: list[str], offset: int) -> tuple[int, str] | str:
    """Find where a docstring would go in ``node``.

    Returns ``(index, indent)``, or a string explaining why the node is to be
    left alone. The docstring goes right before the first statement of the
    body, which must start its own line.
    """
    first = node.body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
        if isinstance(first.value.value, str):
            return "already has a docstring (not Momus's to replace)"
    line_number = _first_line(first) + offset
    line = lines[line_number - 1]
    indent = line[: len(line) - len(line.lstrip(" \t"))]
    decorated = bool(getattr(first, "decorator_list", None))
    # ast columns count UTF-8 bytes, so compare in bytes.
    starts_line = (
        line.lstrip().startswith("@")
        if decorated
        else first.col_offset == len(indent.encode("utf-8"))
    )
    if not starts_line or not indent:
        return "the body does not start on its own indented line"
    return line_number - 1, indent


def _code_of(node: ast.stmt, piece_lines: list[str]) -> str:
    start, end = _first_line(node), node.end_lineno
    return textwrap.dedent("".join(piece_lines[start - 1 : end]))


def _targets(source: str, lines: list[str]) -> tuple[list[_Target], list[Outcome]]:
    """List what needs a docstring, and what was left alone and why."""
    targets: list[_Target] = []
    skipped: list[Outcome] = []

    def consider(node, name, kind, context, piece_lines, offset):
        slot = _slot(node, lines, offset)
        if isinstance(slot, str):
            skipped.append(Outcome(name, SKIPPED, slot))
            return
        index, indent = slot
        targets.append(_Target(name, kind, _code_of(node, piece_lines), context, index, indent))

    for piece in split_source(source):
        if piece.kind not in ("function", "class"):
            continue
        piece_lines = argus.split_lines(piece.text)
        offset = piece.start_line - 1
        node = ast.parse(piece.text).body[0]
        if piece.kind == "function":
            consider(node, node.name, "function", "", piece_lines, offset)
            continue
        consider(
            node,
            node.name,
            "class",
            "Document the class as a whole; its methods are documented separately.\n\n",
            piece_lines,
            offset,
        )
        for child in node.body:
            if isinstance(child, _FUNCTIONS):
                consider(
                    child,
                    f"{node.name}.{child.name}",
                    "method",
                    f"This method belongs to the class {node.name}.\n\n",
                    piece_lines,
                    offset,
                )
    return targets, skipped


# --- Inserting and checking ------------------------------------------------


def _ending_of(lines: list[str], index: int) -> str:
    match = _ENDING.search(lines[index])
    if match:
        return match.group()
    for line in lines:
        match = _ENDING.search(line)
        if match:
            return match.group()
    return "\n"


def _insert(lines: list[str], insertions: list[tuple[int, list[str]]]) -> tuple[str, list[int]]:
    """Insert blocks of lines before the given 0-based indexes, in one pass.

    Returns the new text and the 1-based numbers of the inserted lines in it.
    """
    result: list[str] = []
    numbers: list[int] = []
    pending = dict(insertions)
    for index, line in enumerate(lines):
        block = pending.get(index)
        if block:
            numbers.extend(range(len(result) + 1, len(result) + len(block) + 1))
            result.extend(block)
        result.append(line)
    return "".join(result), numbers


def _passes_guard(original: str, new: str, inserted: list[int]) -> str | None:
    """Run both Argus checks; return the reason for a failure, or None."""
    for verdict in (
        argus.compare_code(original, new),
        argus.check_inserted_lines(original, new, inserted),
    ):
        if not verdict.accepted:
            return verdict.reason
    return None


def comment_source(source: str, backend: Backend) -> ClioResult:
    """Add a docstring to every function, method and class that lacks one.

    Each docstring is generated by ``backend``, inserted by this function and
    verified by Argus on its own; one that fails is dropped without affecting
    the others. A final check covers the combined result. A file that cannot
    be split is returned unchanged with no outcomes.
    """
    try:
        lines = argus.split_lines(source)
        targets, outcomes = _targets(source, lines)
    except (SplitError, argus.ArgusError) as exc:
        return ClioResult(source, (Outcome("<file>", SKIPPED, f"not processed: {exc}"),), ())

    accepted: list[tuple[_Target, list[str]]] = []
    for target in targets:
        prompt = build_prompt(target.kind, target.code, target.context)
        try:
            text = parse_reply(backend.complete(prompt))
            block = format_docstring(text, target.indent, _ending_of(lines, target.index))
        except (BackendError, ClioError) as exc:
            outcomes.append(Outcome(target.name, REJECTED, str(exc)))
            continue
        candidate, inserted = _insert(lines, [(target.index, block)])
        failure = _passes_guard(source, candidate, inserted)
        if failure:
            outcomes.append(Outcome(target.name, REJECTED, failure))
            continue
        accepted.append((target, block))

    if not accepted:
        return ClioResult(source, tuple(outcomes), ())
    text, inserted = _insert(lines, [(target.index, block) for target, block in accepted])
    failure = _passes_guard(source, text, inserted)
    if failure:
        # Should not happen, since each piece passed alone. If it does, keep
        # nothing: the original file is the only text known to be safe.
        outcomes.extend(Outcome(t.name, REJECTED, f"combined check: {failure}") for t, _ in accepted)
        return ClioResult(source, tuple(outcomes), ())
    outcomes.extend(Outcome(t.name, ADDED, "docstring added") for t, _ in accepted)
    return ClioResult(text, tuple(outcomes), tuple(inserted))


# --- Files -----------------------------------------------------------------


def read_text_exact(path: Path) -> str:
    """Read a file as UTF-8 without touching its line endings.

    Raises:
        ClioError: if the file is not valid UTF-8.
    """
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.read()
    except UnicodeDecodeError as exc:
        raise ClioError(f"{path} is not valid UTF-8") from exc


def write_text_atomic(path: Path, text: str) -> None:
    """Replace ``path`` with ``text`` so a crash never leaves a half-written file.

    The text goes to a temporary file in the same folder, which then replaces
    the original in one step. The original's permissions are kept and line
    endings are written exactly as given.
    """
    folder = path.resolve().parent
    handle, temp_name = tempfile.mkstemp(dir=folder, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as temp:
            temp.write(text)
        shutil.copymode(path, temp_name)
        os.replace(temp_name, path)
    except BaseException:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        raise
