"""Clio, the commenting stage: adds missing docstrings and inline comments.

The model never writes code and never decides where anything goes. For a
docstring it returns only the text. For inline comments it is shown the code
with numbered statements (S1, S2, ...) and answers "S3: comment text". Momus
finds the place with ``ast`` line numbers and inserts the lines itself. Every
insertion is then checked twice by Argus (the code is identical, and removing
the inserted lines gives back the original text exactly), and anything that
fails is dropped.

Nothing here writes to a file except ``write_text_atomic``, which callers use
only after the checks have passed.
"""

import ast
import io
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import tokenize
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from momus import argus
from momus.backends import Backend, BackendError
from momus.cleaning import clean_output, strip_reasoning
from momus.quality import (
    comment_problem,
    copied_from_instructions,
    is_placeholder,
    polish_docstring,
)
from momus.splitter import split_source

ADDED = "added"
SKIPPED = "skipped"
REJECTED = "rejected"

# What to generate. "both" asks for docstrings first, then comments.
MODES = ("both", "docstrings", "comments")
# Docstrings only, unless asked. Inline comments double the model calls and,
# after the quality rules, very few survive (measured 2026-11-13 on two
# models), so they are an opt-in until that changes.
DEFAULT_MODE = "docstrings"

# A function with fewer numbered statements than this is not offered for
# comments: there is little to explain, and small models over-comment.
MIN_STATEMENTS = 3

# The most comments accepted for one function. The prompt asks for this too,
# but small models do not always count, so the code enforces it.
MAX_COMMENTS = 3

# Width of a docstring line, counting the indentation.
DOCSTRING_WIDTH = 79

_DOC_MARKER = re.compile(r"\A\s*DOCSTRING:[ \t]*", re.IGNORECASE)
_COMMENTS_MARKER = re.compile(r"\A\s*COMMENTS:[ \t]*", re.IGNORECASE)
# "S3: text" (a dash, dot or parenthesis after the number is tolerated too).
_ENTRY = re.compile(r"^\s*S(\d+)\s*[:.)-]\s*(.*\S)\s*$")
# Where a model starts repeating the code after its answer: a "Code:" label or
# a fence. The answer ends there.
_ECHO = re.compile(r"^(?:[ \t]*```|Code:)", re.MULTILINE)
_ENDING = re.compile(r"\r\n|\r|\n")
# A list entry such as "name: what it is" or "name (type): what it is".
_ENTRY_LINE = re.compile(r"\s*[\w*]+( \([^)]*\))?:\s")
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_DEFINITIONS = (*_FUNCTIONS, ast.ClassDef)


class ClioError(Exception):
    """Raised for a model reply that cannot be used."""


@dataclass(frozen=True)
class Outcome:
    """What happened to one function, method, class or comment."""

    name: str
    status: str  # ADDED, SKIPPED (left alone on purpose) or REJECTED (a check failed)
    reason: str
    kind: str = ""  # "docstring" or "comment"; empty for a whole-file outcome
    cause: str = ""  # for REJECTED: "backend", "reply", "anchor", "style", "limit" or "guard"


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


@dataclass(frozen=True)
class _CommentTarget:
    name: str
    kind: str  # "function" or "method"
    code: str  # source shown to the model, with statement numbers in a left column
    context: str
    slots: dict  # statement number -> (0-based line index, indent, the statement's text)


# --- Prompts and replies ---------------------------------------------------


def _load(name: str) -> str:
    """Read a prompt template; they live in plain files so they are easy to edit."""
    return resources.files("momus").joinpath(f"prompts/{name}").read_text(encoding="utf-8")


def _fill(template: str, **values: str) -> str:
    """Fill ``{{NAME}}`` markers by plain replacement, because code is full of braces."""
    for key, value in values.items():
        template = template.replace("{{" + key.upper() + "}}", value)
    return template


def load_prompt() -> str:
    """Read the docstring prompt template."""
    return _load("clio.txt")


def build_prompt(kind: str, code: str, context: str = "") -> str:
    """Fill the docstring prompt."""
    return _fill(load_prompt(), kind=kind, context=context, code=code)


def build_comment_prompt(kind: str, code: str, context: str = "") -> str:
    """Fill the inline-comment prompt; ``code`` carries the statement numbers."""
    return _fill(_load("clio_comments.txt"), kind=kind, context=context, code=code)


def _after_marker(reply: str, marker: re.Pattern, label: str) -> str:
    """Return the part of a reply that follows ``marker``, without echoed code.

    Raises:
        ClioError: if the marker is not there.
    """
    text = strip_reasoning(reply)
    match = marker.match(text)
    if match is None:
        # Perhaps the whole answer is inside a fence, or has a sentence before it.
        text = clean_output(text)
        match = marker.match(text)
    if match is None:
        raise ClioError(f"reply does not start with {label}")
    # Read the marker before looking at fences: a model often repeats the code
    # in a fence after its answer, and that fence is not the answer.
    return _ECHO.split(text[match.end() :], maxsplit=1)[0]


def parse_reply(reply: str) -> str:
    """Extract the docstring text from a model reply.

    The reply must contain a ``DOCSTRING:`` line followed by the text. Quotes
    the model put around the text are removed, and so is any copy of the code
    the model repeated after its answer.

    Raises:
        ClioError: if the marker is missing, the text is empty, or it contains
            a triple double quote, which would end the docstring early.
    """
    text = textwrap.dedent(_after_marker(reply, _DOC_MARKER, "DOCSTRING:")).strip()
    for quote in ('"""', "'''"):
        if text.startswith(quote) and text.endswith(quote) and len(text) >= 2 * len(quote):
            text = text[len(quote) : -len(quote)].strip()
            break
    if not text:
        raise ClioError("the docstring is empty")
    if is_placeholder(text):
        raise ClioError("the reply repeats the template instead of answering it")
    if '"""' in text:
        raise ClioError("the docstring contains a triple double quote")
    # A backslash would be read as an escape; doubling keeps the intended text.
    return polish_docstring(text).replace("\\", "\\\\")


def parse_comments(reply: str) -> list[tuple[int, str]]:
    """Extract ``(statement number, comment text)`` pairs from a model reply.

    The reply must contain a ``COMMENTS:`` line, followed by ``S3: text``
    lines, or by ``NONE``. A leading ``#`` in the text is removed. The numbers
    are not checked here: a number that points at nothing is the caller's
    business, because it is worth counting.

    Raises:
        ClioError: if the marker is missing, or there is text but no line in
            the ``S3: text`` format.
    """
    entries: list[tuple[int, str]] = []
    unmatched = False
    for line in _after_marker(reply, _COMMENTS_MARKER, "COMMENTS:").splitlines():
        if not line.strip() or line.strip().upper() == "NONE":
            continue
        match = _ENTRY.match(line)
        if match is None:
            unmatched = True
            continue
        text = " ".join(match.group(2).lstrip("# \t").split())
        entries.append((int(match.group(1)), text))
    if unmatched and not entries:
        raise ClioError("no line in the S<number>: <text> format")
    return entries


def _wrap(line: str, width: int) -> list[str]:
    """Wrap one line to ``width``, keeping its indentation.

    The continuation of a list entry is indented four more, so the entry's
    name stays visible.
    """
    if len(line) <= width:
        return [line]
    lead = len(line) - len(line.lstrip())
    extra = 4 if _ENTRY_LINE.match(line) else 0
    return textwrap.wrap(
        line,
        width=width,
        subsequent_indent=" " * (lead + extra),
        break_long_words=False,
        break_on_hyphens=False,
    ) or [line]


def format_docstring(text: str, indent: str, newline: str) -> list[str]:
    """Lay out ``text`` as the lines of a triple-quoted docstring.

    Lines are wrapped so that none passes ``DOCSTRING_WIDTH`` columns, which
    only changes where the text breaks.
    """
    width = DOCSTRING_WIDTH - len(indent)
    lines: list[str] = []
    for position, raw in enumerate(text.split("\n")):
        # The first line also carries the opening quotes.
        lines.extend(_wrap(raw.rstrip(), width - 3 if position == 0 else width))
    # The closing quotes go on their own line when the text ends in a quote
    # mark, because ``"..."`"""`` would end the string in the wrong place.
    if len(lines) == 1 and not lines[0].endswith('"'):
        return [f'{indent}"""{lines[0]}"""{newline}']
    body = [f"{indent}{line}{newline}" if line else newline for line in lines[1:]]
    return [f'{indent}"""{lines[0]}{newline}', *body, f'{indent}"""{newline}']


def format_comment(text: str, indent: str, newline: str) -> list[str]:
    """Lay out ``text`` as one or more ``#`` lines, wrapped to about 79 columns."""
    width = max(20, 79 - len(indent) - 2)
    return [f"{indent}# {line}{newline}" for line in textwrap.wrap(text, width=width)]


# --- Finding where things go -----------------------------------------------


def _first_line(node: ast.stmt) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *(decorator.lineno for decorator in decorators)])


def _is_docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _starts_line(statement: ast.stmt, line: str, indent: str) -> bool:
    """Tell whether ``statement`` is the first thing on its (indented) line."""
    if not indent:
        return False
    if getattr(statement, "decorator_list", None):
        return line.lstrip().startswith("@")
    # ast columns count UTF-8 bytes, so compare in bytes.
    return statement.col_offset == len(indent.encode("utf-8"))


def _slot(node: ast.AST, lines: list[str], offset: int) -> tuple[int, str] | str:
    """Find where a docstring would go in ``node``.

    Returns ``(index, indent)``, or a string explaining why the node is to be
    left alone. The docstring goes right before the first statement of the
    body, which must start its own line.
    """
    first = node.body[0]
    if _is_docstring(first):
        return "already has a docstring (not Momus's to replace)"
    line_number = _first_line(first) + offset
    line = lines[line_number - 1]
    indent = _indent_of(line)
    if not _starts_line(first, line, indent):
        return "the body does not start on its own indented line"
    return line_number - 1, indent


def _statements(body: list[ast.stmt]) -> list[ast.stmt]:
    """List the statements of a body in source order, nested blocks included.

    Nested functions and classes count as one statement each and are not
    entered: they are not targets of their own yet.
    """
    found: list[ast.stmt] = []

    def visit(statements):
        for statement in statements:
            found.append(statement)
            if isinstance(statement, _DEFINITIONS):
                continue
            for field in ("body", "orelse", "finalbody"):
                visit(getattr(statement, field, None) or [])
            for handler in getattr(statement, "handlers", None) or []:
                visit(handler.body)
            for case in getattr(statement, "cases", None) or []:
                visit(case.body)

    visit(body)
    return sorted(found, key=_first_line)


def _comment_slot(statement: ast.stmt, lines: list[str], offset: int, commented: set[int]):
    """Return ``(index, indent)`` if a comment may go above ``statement``, else None.

    Not offered: statements that share a line with another, ``elif`` branches,
    and any statement that already has a comment above it or on its line. A
    comment written by someone else is never joined or replaced.
    """
    number = _first_line(statement) + offset
    line = lines[number - 1]
    indent = _indent_of(line)
    if not _starts_line(statement, line, indent):
        return None
    if isinstance(statement, ast.If) and line.lstrip().startswith("elif"):
        return None
    if number in commented or (number >= 2 and lines[number - 2].lstrip().startswith("#")):
        return None
    return number - 1, indent


def _numbered(node: ast.stmt, piece_lines: list[str], numbers: dict[int, int], offset: int) -> str:
    """Show ``node`` with a left column holding the statement numbers.

    ``numbers`` maps an absolute 1-based line number to its statement number.
    """
    start, end = _first_line(node), node.end_lineno
    indent = _indent_of(piece_lines[start - 1])
    rows = []
    for number in range(start, end + 1):
        text = piece_lines[number - 1].rstrip("\r\n")
        text = text[len(indent) :] if text.startswith(indent) else text
        label = f"S{numbers[number + offset]}" if (number + offset) in numbers else ""
        rows.append(f"{label:<5}| {text}")
    return "\n".join(rows) + "\n"


def _code_of(node: ast.stmt, piece_lines: list[str]) -> str:
    start, end = _first_line(node), node.end_lineno
    return textwrap.dedent("".join(piece_lines[start - 1 : end]))


def _commented_lines(source: str) -> set[int]:
    """Return the 1-based numbers of the lines that carry a ``#`` comment."""
    reader = io.StringIO(source, newline="").readline
    return {
        token.start[0]
        for token in tokenize.generate_tokens(reader)
        if token.type == tokenize.COMMENT
    }


def _targets(source: str, lines: list[str], want_comments: bool):
    """List what needs a docstring or comments, and what was left alone and why."""
    doc_targets: list[_Target] = []
    comment_targets: list[_CommentTarget] = []
    doc_skips: list[Outcome] = []
    comment_skips: list[Outcome] = []
    commented = _commented_lines(source) if want_comments else set()

    def consider(node, name, kind, context, piece_lines, offset):
        slot = _slot(node, lines, offset)
        if isinstance(slot, str):
            doc_skips.append(Outcome(name, SKIPPED, slot, "docstring"))
        else:
            index, indent = slot
            code = _code_of(node, piece_lines)
            doc_context = context
            if kind == "method":
                # Show the class as code around the method instead of saying it
                # in a sentence: small models copy such sentences into the
                # docstring.
                owner = name.split(".", 1)[0]
                code = f"class {owner}:\n    ...\n\n{textwrap.indent(code, '    ')}"
                doc_context = ""
            doc_targets.append(_Target(name, kind, code, doc_context, index, indent))
        if not want_comments or kind == "class":
            return
        eligible = []
        for position, statement in enumerate(_statements(node.body)):
            if position == 0 and _is_docstring(statement):
                continue
            found = _comment_slot(statement, lines, offset, commented)
            if found:
                first = _first_line(statement)
                last = min(statement.end_lineno, first + 5)  # a compound statement: its start
                eligible.append((*found, "".join(piece_lines[first - 1 : last])))
        if len(eligible) < MIN_STATEMENTS:
            comment_skips.append(
                Outcome(f"{name} comments", SKIPPED, "too few statements to comment", "comment")
            )
            return
        slots = dict(enumerate(eligible, start=1))
        numbers = {index + 1: number for number, (index, _, _) in slots.items()}
        code = _numbered(node, piece_lines, numbers, offset)
        comment_targets.append(_CommentTarget(name, kind, code, context, slots))

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
    return doc_targets, comment_targets, doc_skips, comment_skips


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

    Blocks given for the same index go in the order given. Returns the new
    text and the 1-based numbers of the inserted lines in it.
    """
    pending: dict[int, list[str]] = {}
    for index, block in insertions:
        pending.setdefault(index, []).extend(block)
    result: list[str] = []
    numbers: list[int] = []
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


def _instructions(prompt: str) -> str:
    """Return the part of a prompt that comes before the code."""
    return prompt.rsplit("\nCode:\n", 1)[0]


def _cause_of(error: Exception) -> str:
    """Name where a failure came from: the server, or the shape of the reply."""
    return "backend" if isinstance(error, BackendError) else "reply"


def _sits_above(new: str, inserted: list[int], original_line: str) -> bool:
    """Tell whether the line right after the inserted block is ``original_line``."""
    new_lines = argus.split_lines(new)
    return inserted[-1] < len(new_lines) and new_lines[inserted[-1]] == original_line


def comment_source(source: str, backend: Backend, mode: str = DEFAULT_MODE) -> ClioResult:
    """Add missing docstrings, and inline comments if asked, to ``source``.

    ``mode`` is ``"docstrings"`` (the default), ``"comments"`` or ``"both"``. Text comes from
    ``backend``; Momus does the inserting and Argus the verifying. Each
    insertion is checked on its own, and one that fails is dropped without
    affecting the others. A final check covers the combined result. A file
    that cannot be analysed is returned unchanged.

    Raises:
        ValueError: if ``mode`` is not one of ``MODES``.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    want_docstrings = mode in ("both", "docstrings")
    want_comments = mode in ("both", "comments")
    try:
        lines = argus.split_lines(source)
        doc_targets, comment_targets, doc_skips, comment_skips = _targets(
            source, lines, want_comments
        )
    except Exception as exc:  # parse, split and tokenize errors all mean "leave it"
        return ClioResult(source, (Outcome("<file>", SKIPPED, f"not processed: {exc}"),), ())

    outcomes: list[Outcome] = []
    if want_docstrings:
        outcomes.extend(doc_skips)
    else:
        doc_targets = []
    if want_comments:
        outcomes.extend(comment_skips)

    accepted: list[tuple[str, int, list[str], str]] = []

    def try_insert(
        name: str, kind: str, index: int, block: list[str], original_line: str | None
    ) -> None:
        candidate, inserted = _insert(lines, [(index, block)])
        failure = _passes_guard(source, candidate, inserted)
        if failure is None and original_line is not None:
            if not _sits_above(candidate, inserted, original_line):
                failure = "the comment is not directly above its statement"
        if failure:
            outcomes.append(Outcome(name, REJECTED, failure, kind, "guard"))
        else:
            accepted.append((name, index, block, kind))

    # Docstrings are handled first, so that when a docstring and a comment land
    # before the same line, the docstring is the one above.
    for target in doc_targets:
        prompt = build_prompt(target.kind, target.code, target.context)
        try:
            text = parse_reply(backend.complete(prompt))
            if copied_from_instructions(text, _instructions(prompt)):
                raise ClioError("the text is copied from the instructions")
        except (BackendError, ClioError) as exc:
            outcomes.append(
                Outcome(target.name, REJECTED, str(exc), "docstring", _cause_of(exc))
            )
            continue
        block = format_docstring(text, target.indent, _ending_of(lines, target.index))
        try_insert(target.name, "docstring", target.index, block, None)

    for target in comment_targets:
        prompt = build_comment_prompt(target.kind, target.code, target.context)
        label = f"{target.name} comments"
        try:
            entries = parse_comments(backend.complete(prompt))
        except (BackendError, ClioError) as exc:
            outcomes.append(Outcome(label, REJECTED, str(exc), "comment", _cause_of(exc)))
            continue
        if not entries:
            outcomes.append(Outcome(label, SKIPPED, "the model proposed no comments", "comment"))
        seen: set[int] = set()
        taken = 0
        for number, text in entries:
            name = f"{target.name} S{number}"
            if taken >= MAX_COMMENTS:
                outcomes.append(
                    Outcome(name, REJECTED, f"more than {MAX_COMMENTS} comments", "comment", "limit")
                )
                continue
            if number in seen:
                outcomes.append(
                    Outcome(name, REJECTED, "the statement was named twice", "comment", "anchor")
                )
                continue
            seen.add(number)
            if number not in target.slots:
                outcomes.append(
                    Outcome(name, REJECTED, "not a numbered statement", "comment", "anchor")
                )
                continue
            if not text:
                outcomes.append(
                    Outcome(name, REJECTED, "the comment is empty", "comment", "reply")
                )
                continue
            index, indent, statement = target.slots[number]
            if copied_from_instructions(text, _instructions(prompt)):
                outcomes.append(
                    Outcome(name, REJECTED, "copied from the instructions", "comment", "reply")
                )
                continue
            problem = comment_problem(text, statement)
            if problem:
                outcomes.append(Outcome(name, REJECTED, problem, "comment", "style"))
                continue
            block = format_comment(text, indent, _ending_of(lines, index))
            taken += 1
            try_insert(name, "comment", index, block, lines[index])

    if not accepted:
        return ClioResult(source, tuple(outcomes), ())
    text, inserted = _insert(lines, [(index, block) for _, index, block, _ in accepted])
    failure = _passes_guard(source, text, inserted)
    if failure:
        # Should not happen, since each insertion passed alone. If it does,
        # keep nothing: the original file is the only text known to be safe.
        outcomes.extend(
            Outcome(n, REJECTED, f"combined check: {failure}", k, "guard")
            for n, _, _, k in accepted
        )
        return ClioResult(source, tuple(outcomes), ())
    outcomes.extend(Outcome(name, ADDED, "added", kind) for name, _, _, kind in accepted)
    return ClioResult(text, tuple(outcomes), tuple(inserted))


# --- Files -----------------------------------------------------------------


# Runs a git command in `folder` and returns what it printed. Raises ClioError
# if git cannot be run or reports a failure.
def _git(folder: Path, *args: str) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(folder), *args], capture_output=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ClioError(f"cannot run git: {exc}") from exc
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise ClioError(detail[0] if detail else "git failed")
    return done.stdout.decode("utf-8", errors="surrogateescape")


# Lists the `.py` files that differ from the last commit, anywhere in the
# repository that holds `folder`, sorted by name: the files git tracks whose
# content, staged or not, is not the one in `HEAD`, and the new files git does
# not track yet. Deleted files are left out, and so is anything `.gitignore`
# excludes. Raises ClioError if `folder` is not in a git repository, the
# repository has no commit yet, or git cannot be run.
def changed_python_files(folder: Path = Path(".")) -> list[Path]:
    top = Path(_git(folder, "rev-parse", "--show-toplevel").rstrip("\r\n"))
    # -z: names come out as they are, separated by NUL, with no quoting.
    names = set(_git(folder, "diff", "--name-only", "-z", "--diff-filter=d", "HEAD", "--").split("\0"))
    # --exclude-standard: without it git would also list every ignored file,
    # the virtual environment included. Run from the top, because `ls-files`
    # only looks below the folder it is run in.
    names.update(_git(top, "ls-files", "--others", "--exclude-standard", "-z").split("\0"))
    return [top / name for name in sorted(names) if name.endswith(".py")]


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
