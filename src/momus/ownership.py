# Ownership: which comments Momus itself wrote.
#
# Momus may only touch its own comments. To know which those are without
# putting any marker in the code, it keeps a record outside the project (see
# `momus.state`): one line per event, "written" when a comment is written to a
# file and "reviewed" when the reviewer has read it.
#
# A comment is recognised by the file it is in, whether it is a docstring or
# a `#` comment, the qualified name of the function or class it belongs to,
# and a hash of its text. Not by line number, because lines move. The record
# holds no code and no comment text.
#
# Everything errs on the side of "not Momus's": an edited comment has another
# hash, a renamed function another name, a lost record no entries at all. In
# each case the comment is simply left alone.

import ast
import hashlib
import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from momus.critic import Comment, CriticError, find_comments
from momus.state import claim_project_folder, locate, project_folder

RECORD_NAME = "comments.jsonl"
MODULE_NAME = "<module>"
_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


# The hash of a comment's text, blind to how far each line is indented, so
# re-indenting code does not lose ownership.
def comment_hash(text: str) -> str:
    plain = "\n".join(line.strip() for line in text.strip().splitlines())
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


# Every function and class of `tree` with its qualified name ("Box.grow").
def _definitions(tree: ast.Module) -> list[tuple[ast.AST, str]]:
    found: list[tuple[ast.AST, str]] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _DEFINITIONS):
                name = f"{prefix}{child.name}"
                found.append((child, name))
                visit(child, f"{name}.")
            else:
                visit(child, prefix)

    visit(tree, "")
    return found


# The qualified name of what `comment` belongs to: for a docstring, the
# function or class it documents; for a `#` comment, the innermost one whose
# body it is in. `<module>` for the file itself.
def owner_name(definitions: list[tuple[ast.AST, str]], comment: Comment) -> str:
    best, best_line = MODULE_NAME, 0
    for node, name in definitions:
        if comment.kind == "docstring":
            if node.body and node.body[0].lineno == comment.line:
                return name
        elif node.lineno < comment.line <= node.end_lineno and node.lineno > best_line:
            best, best_line = name, node.lineno
    return best


# Reads and writes the record of the project each file belongs to.
class Ownership:
    def __init__(self, home: Path | None = None) -> None:
        self.home = home

    # What identifies each comment that `new` adds to `original`.
    #
    # Raises:
    #     CriticError: if `new` is not `original` plus comments only.
    def _keys(self, path: Path, original: str, new: str) -> list[tuple[Comment, tuple]]:
        _, name = locate(path)
        comments = find_comments(str(path), original, new)
        definitions = _definitions(ast.parse(new)) if comments else []
        return [
            (comment, (name, comment.kind, owner_name(definitions, comment), comment_hash(comment.text)))
            for comment in comments
        ]

    def _record_path(self, path: Path) -> Path:
        root, _ = locate(path)
        return project_folder(root, self.home) / RECORD_NAME

    # The comments on record for the project of `path`, as a set per event.
    def _events(self, path: Path) -> dict[str, set[tuple]]:
        events: dict[str, set[tuple]] = {"written": set(), "reviewed": set()}
        try:
            text = self._record_path(path).read_text(encoding="utf-8")
        except OSError:
            return events
        for line in text.splitlines():
            try:
                entry = json.loads(line)
                key = (entry["file"], entry["kind"], entry["name"], entry["hash"])
                events[entry["event"]].add(key)
            except (ValueError, KeyError, TypeError):
                continue
        return events

    def _append(self, path: Path, event: str, keys: Iterable[tuple]) -> int:
        keys = list(keys)
        if not keys:
            return 0
        try:
            root, _ = locate(path)
            folder = claim_project_folder(root, self.home)
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with open(folder / RECORD_NAME, "a", encoding="utf-8") as handle:
                for file, kind, name, digest in keys:
                    entry = {"time": now, "event": event, "file": file, "kind": kind, "name": name, "hash": digest}
                    handle.write(json.dumps(entry) + "\n")
        except Exception:  # a record that cannot be written means "not Momus's": safe
            return 0
        return len(keys)

    # Record that Momus wrote the comments `new` adds to `original`. Returns
    # how many were recorded; never raises.
    def record_written(self, path: Path, original: str, new: str) -> int:
        try:
            keys = [key for _, key in self._keys(path, original, new)]
        except (CriticError, SyntaxError, ValueError):
            return 0
        return self._append(path, "written", keys)

    # The comments that `new` adds to `original` and that Momus wrote, as
    # `(first line, last line)` pairs in `new`. With `unreviewed`, only those
    # the reviewer has not read yet. Empty if anything cannot be established.
    def select(self, path: Path, original: str, new: str, unreviewed: bool = False) -> set[tuple[int, int]]:
        try:
            keyed = self._keys(path, original, new)
        except (CriticError, SyntaxError, ValueError):
            return set()
        events = self._events(path)
        return {
            (comment.line, comment.end_line)
            for comment, key in keyed
            if key in events["written"] and not (unreviewed and key in events["reviewed"])
        }

    # Record that the reviewer has read `comments` (those of them Momus
    # wrote). Returns how many were recorded; never raises.
    def record_reviewed(self, path: Path, original: str, new: str, comments: Iterable[Comment]) -> int:
        read = {(comment.line, comment.end_line) for comment in comments}
        try:
            keyed = self._keys(path, original, new)
        except (CriticError, SyntaxError, ValueError):
            return 0
        events = self._events(path)
        keys = [
            key
            for comment, key in keyed
            if (comment.line, comment.end_line) in read
            and key in events["written"]
            and key not in events["reviewed"]
        ]
        return self._append(path, "reviewed", keys)
