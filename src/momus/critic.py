"""The critic: asks a strong model whether the comments Momus added are any good.

Clio's comments are written by a small model and nothing proves they are true,
so a stronger model reads them. To keep that cheap it is not shown the whole
file: only the comments Momus added, each next to the code of the function or
class around it. The code has to be there. A well-written false comment cannot
be recognised without it.

Review only ever looks at a change that adds comments and docstrings and
nothing else. Anything more is refused, using the same two checks as Argus.
"""

import ast
import difflib
import re
import subprocess
import textwrap
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from momus import argus
from momus.backends import Backend, BackendError
from momus.cleaning import clean_output, strip_reasoning

# A definition longer than this is shown only around its comments.
MAX_CONTEXT_LINES = 60
CONTEXT_MARGIN = 12
# Lines shown around a comment that is not inside any function or class.
MODULE_MARGIN = 5
# Rough limit on the size of one request, in characters of code shown.
MAX_BATCH_CHARS = 12000

_ENTRY = re.compile(r"^\s*C(\d+)\s*[:.)-]\s*(.*\S)\s*$")
_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


class CriticError(Exception):
    """Raised when a change cannot be reviewed, or a reply cannot be used."""


@dataclass(frozen=True)
class Comment:
    """A docstring or a block of ``#`` lines that was added to a file."""

    path: str
    kind: str  # "docstring" or "comment"
    line: int  # 1-based line in the new text where it starts
    end_line: int
    text: str


@dataclass(frozen=True)
class Group:
    """Comments that share one piece of code, and that code ready to show."""

    path: str
    code: str
    comments: tuple[Comment, ...]


@dataclass(frozen=True)
class Finding:
    """One problem the reviewer reported."""

    path: str
    line: int
    kind: str
    problem: str
    text: str  # the comment it is about

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.problem}"


@dataclass
class ReviewResult:
    """What a review produced: findings, how much was reviewed, what went wrong."""

    findings: list[Finding] = field(default_factory=list)
    reviewed: int = 0
    batches: int = 0
    errors: list[str] = field(default_factory=list)


# --- Finding what was added ------------------------------------------------


def _inserted_lines(old_lines: list[str], new_lines: list[str]) -> list[int]:
    """Return the 1-based numbers of the lines that were only added.

    Raises:
        CriticError: if any line was changed or removed.
    """
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    inserted: list[int] = []
    for tag, _, _, new_start, new_end in matcher.get_opcodes():
        if tag == "insert":
            inserted.extend(range(new_start + 1, new_end + 1))
        elif tag != "equal":
            raise CriticError("not a comments-only change: lines were changed or removed")
    return inserted


def find_comments(path: str, original: str, new: str) -> list[Comment]:
    """List the docstrings and comments that ``new`` adds to ``original``.

    Raises:
        CriticError: if ``new`` is not ``original`` plus comments and
            docstrings only. Both Argus checks must pass, so a change that
            touches the code is never reviewed as if it were harmless.
    """
    old_lines, new_lines = argus.split_lines(original), argus.split_lines(new)
    inserted = _inserted_lines(old_lines, new_lines)
    for verdict in (
        argus.compare_code(original, new),
        argus.check_inserted_lines(original, new, inserted),
    ):
        if not verdict.accepted:
            raise CriticError(f"not a comments-only change: {verdict.reason}")

    remaining = set(inserted)
    comments: list[Comment] = []
    tree = ast.parse(new)
    for owner in ast.walk(tree):
        if not isinstance(owner, (ast.Module, *_DEFINITIONS)) or not owner.body:
            continue
        first = owner.body[0]
        is_docstring = (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        )
        span = range(first.lineno, first.end_lineno + 1) if is_docstring else range(0)
        if is_docstring and all(n in remaining for n in span):
            text = textwrap.dedent("".join(new_lines[first.lineno - 1 : first.end_lineno])).strip()
            comments.append(Comment(path, "docstring", first.lineno, first.end_lineno, text))
            remaining.difference_update(span)

    block: list[int] = []

    def close() -> None:
        if block:
            text = " ".join(new_lines[n - 1].strip().lstrip("#").strip() for n in block)
            comments.append(Comment(path, "comment", block[0], block[-1], text))
            block.clear()

    for number in sorted(remaining):
        content = new_lines[number - 1].strip()
        if not content:
            close()
        elif content.startswith("#"):
            if block and number != block[-1] + 1:
                close()
            block.append(number)
        else:
            raise CriticError(f"unexpected added text at line {number}")
    close()
    return sorted(comments, key=lambda comment: comment.line)


# --- Showing the code around them ------------------------------------------


def _first_line(node: ast.stmt) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *(decorator.lineno for decorator in decorators)])


def _enclosing(tree: ast.Module, line: int):
    """Return the innermost function or class that contains ``line``, or None."""
    best = None
    for node in ast.walk(tree):
        if isinstance(node, _DEFINITIONS) and _first_line(node) <= line <= node.end_lineno:
            if best is None or _first_line(node) >= _first_line(best):
                best = node
    return best


def _render(new_lines: list[str], first: int, last: int, added: set[int]) -> str:
    """Show lines ``first``..``last`` with their numbers; ``+`` marks added lines."""
    return "\n".join(
        f"{number:>5}{'+' if number in added else ' '}| {new_lines[number - 1].rstrip()}"
        for number in range(first, last + 1)
    )


def _mark_omissions(code, new_lines, added, owner, span, first, last) -> str:
    """Say which lines of a definition were left out of ``code``.

    Without this the reviewer takes the part it sees for the whole, and
    reports a method as nonexistent because it was cut off. For a class, the
    signatures of the methods that were cut are listed, so a docstring about
    the class can still be checked against what the class offers.
    """
    start, end = span
    if first > start:
        code = f"      ... lines {start}-{first - 1} of this definition are not shown\n{code}"
    if last < end:
        code += f"\n      ... lines {last + 1}-{end} of this definition are not shown"
        signatures = []
        if isinstance(owner, ast.ClassDef):
            for child in owner.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and _first_line(child) > last:
                    signature_end = max(_first_line(child), child.body[0].lineno - 1)
                    signatures.append(_render(new_lines, _first_line(child), signature_end, added))
        if signatures:
            code += "; the signatures of its methods there:\n" + "\n".join(signatures)
    return code


def build_groups(path: str, original: str, new: str) -> list[Group]:
    """Pair each added comment with the code around it.

    Comments inside the same function or class share one copy of its code. A
    definition longer than ``MAX_CONTEXT_LINES`` is cut down to the part near
    its comments.

    Raises:
        CriticError: as ``find_comments``.
    """
    comments = find_comments(path, original, new)
    if not comments:
        return []
    new_lines = argus.split_lines(new)
    added = {n for c in comments for n in range(c.line, c.end_line + 1)}
    tree = ast.parse(new)

    spans: dict[tuple[int, int] | tuple[str, int], list[Comment]] = {}
    owners: dict = {}
    for comment in comments:
        owner = _enclosing(tree, comment.line)
        if owner is None:
            # Module level: a window around the comment alone.
            key = ("module", comment.line)
        else:
            key = (_first_line(owner), owner.end_lineno)
            owners[key] = owner
        spans.setdefault(key, []).append(comment)

    groups = []
    for key, members in spans.items():
        if key[0] == "module":
            first = max(1, members[0].line - MODULE_MARGIN)
            last = min(len(new_lines), members[-1].end_line + MODULE_MARGIN)
        else:
            first, last = key
            if last - first + 1 > MAX_CONTEXT_LINES:
                first = max(first, members[0].line - CONTEXT_MARGIN)
                last = min(last, members[-1].end_line + CONTEXT_MARGIN)
        code = _render(new_lines, first, last, added)
        if key[0] != "module":
            code = _mark_omissions(code, new_lines, added, owners[key], key, first, last)
        groups.append(Group(path, code, tuple(members)))
    return sorted(groups, key=lambda group: group.comments[0].line)


# --- Asking the reviewer ---------------------------------------------------


@dataclass(frozen=True)
class Batch:
    """One request: the prompt, and which comment each ``C<number>`` means."""

    prompt: str
    comments: dict


def _load_prompt() -> str:
    return resources.files("momus").joinpath("prompts/critic.txt").read_text(encoding="utf-8")


def build_batches(groups: Iterable[Group], max_items: int = 10) -> list[Batch]:
    """Pack groups into requests of at most ``max_items`` comments each.

    A request also stops growing when its code passes ``MAX_BATCH_CHARS``. One
    group always stays whole, even if it alone is over a limit.
    """
    batches: list[list[Group]] = []
    items = size = 0
    for group in groups:
        if batches and (
            items + len(group.comments) > max_items or size + len(group.code) > MAX_BATCH_CHARS
        ):
            batches.append([])
            items = size = 0
        if not batches:
            batches.append([])
        batches[-1].append(group)
        items += len(group.comments)
        size += len(group.code)

    template = _load_prompt()
    result = []
    for members in batches:
        numbered: dict[int, Comment] = {}
        parts = []
        for group in members:
            lines = [f"=== {group.path}", group.code, "", "Comments to check in this code:"]
            for comment in group.comments:
                number = len(numbered) + 1
                numbered[number] = comment
                lines.append(f"C{number} (line {comment.line}, {comment.kind}): {comment.text}")
            parts.append("\n".join(lines))
        result.append(Batch(template.replace("{{BODY}}", "\n\n".join(parts)), numbered))
    return result


def parse_findings(reply: str) -> list[tuple[int, str]]:
    """Read ``C3: problem`` lines from a reply; ``OK`` means no problems.

    Raises:
        CriticError: if the reply has text but no line in that format.
    """
    text = strip_reasoning(reply)
    if "```" in text:
        text = clean_output(text)
    entries: list[tuple[int, str]] = []
    other = False
    for line in text.splitlines():
        if not line.strip():
            continue
        match = _ENTRY.match(line)
        if match:
            entries.append((int(match.group(1)), match.group(2)))
        elif line.strip().rstrip(".").upper() != "OK":
            other = True
    if other and not entries:
        raise CriticError("the reply is neither OK nor C<number>: <problem> lines")
    return entries


def review_changes(
    changes: Iterable[tuple[str, str, str]], backend: Backend, max_items: int = 10
) -> ReviewResult:
    """Review the comments added in ``(path, original, new)`` changes.

    A change that cannot be reviewed, or a request that fails, is recorded in
    ``errors`` and does not stop the others.
    """
    result = ReviewResult()
    groups: list[Group] = []
    for path, original, new in changes:
        try:
            groups.extend(build_groups(path, original, new))
        except (CriticError, argus.ArgusError, SyntaxError, ValueError) as exc:
            result.errors.append(f"{path}: {exc}")
    for batch in build_batches(groups, max_items):
        try:
            entries = parse_findings(backend.complete(batch.prompt))
        except (BackendError, CriticError) as exc:
            result.errors.append(f"review request failed: {exc}")
            continue
        result.batches += 1
        result.reviewed += len(batch.comments)
        for number, problem in entries:
            comment = batch.comments.get(number)
            if comment is None:
                result.errors.append(f"the reviewer mentioned an unknown comment C{number}")
                continue
            result.findings.append(
                Finding(comment.path, comment.line, comment.kind, problem, comment.text)
            )
    result.findings.sort(key=lambda finding: (finding.path, finding.line))
    return result


# --- Where the original text comes from ------------------------------------


def read_git_baseline(path, ref: str = "HEAD") -> str:
    """Return the text of ``path`` as it is in git at ``ref``.

    Raises:
        CriticError: if git cannot provide it (not a repository, new file,
            unknown reference).
    """
    target = Path(path)
    try:
        done = subprocess.run(
            ["git", "-C", str(target.resolve().parent), "show", f"{ref}:./{target.name}"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CriticError(f"cannot run git: {exc}") from exc
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise CriticError(f"no baseline at {ref}: {detail[0] if detail else 'git failed'}")
    try:
        return done.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CriticError("the baseline is not valid UTF-8") from exc
