# Command-line entry point for Momus.
#
# `comment` (docstrings, and inline comments on request), `guard` (check
# that files hold their git baseline plus comments only), `review` (check the
# added comments with a strong model) and `bench` (compare models).

import argparse
import difflib
import os
import sys
from dataclasses import replace
from pathlib import Path

from momus import argus, bench
from momus.backends import Backend, BackendError
from momus.ledger import Ledger
from momus.critic import CriticError, drop_flagged, find_comments, read_git_baseline, review_routed
from momus.clio import (
    DEFAULT_MODE,
    MODES,
    ClioError,
    changed_python_files,
    comment_source,
    read_text_exact,
    write_text_atomic,
)
from momus.config import (
    build_local_backend,
    build_review_backend,
    build_small_review_backend,
    load_local_settings,
    load_review_settings,
)

# Subcommand name -> one-line help.
COMMANDS = {
    "comment": "add comments and docstrings with the local model (Clio)",
    "guard": "check that code is unchanged apart from comments (Argus)",
    "review": "review comments with the strong model (Momus)",
    "bench": "benchmark the local models",
}


# Build the top-level argument parser with one subcommand per stage.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="momus",
        description="Comment and document freshly written code with few tokens.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    for name, help_text in COMMANDS.items():
        sub = subparsers.add_parser(name, help=help_text, description=help_text)
        if name == "comment":
            sub.add_argument(
                "files",
                nargs="*",
                type=Path,
                help="Python files to document (default: the .py files changed or created since the last commit)",
            )
            sub.add_argument(
                "--write",
                action="store_true",
                help="write the changes to the files (default: only show the diff)",
            )
            sub.add_argument("--model", help="model to use instead of the one in momus.toml")
            sub.add_argument(
                "--mode",
                choices=MODES,
                default=DEFAULT_MODE,
                help="what to add: docstrings (default), inline comments, or both",
            )
            sub.add_argument("--config", type=Path, default="momus.toml", help="config file")
        if name == "guard":
            sub.add_argument("files", nargs="+", type=Path, help="files to check")
            sub.add_argument(
                "--base",
                default="HEAD",
                help="git reference holding the files as they were before (default: HEAD)",
            )
            sub.add_argument(
                "--code-only",
                action="store_true",
                help="only require that the code is identical: also accept reformatting and "
                "comments or docstrings that were edited or removed (default: accept added "
                "comments and docstrings only)",
            )
        if name == "review":
            sub.add_argument("files", nargs="+", type=Path, help="files whose new comments to review")
            sub.add_argument(
                "--base",
                default="HEAD",
                help="git reference holding the files as they were before Momus (default: HEAD)",
            )
            sub.add_argument("--config", type=Path, default="momus.toml", help="config file")
            sub.add_argument(
                "--drop",
                action="store_true",
                help="remove the flagged comments from the files (default: only report them). "
                "Every comment added since --base is reviewed, including ones you wrote yourself",
            )
        if name == "bench":
            sub.add_argument(
                "--models",
                nargs="+",
                help="models to compare (default: the four models of the plan)",
            )
            sub.add_argument(
                "--files",
                nargs="+",
                help=f"files to run on (default: {bench.DEFAULT_SAMPLES})",
            )
            sub.add_argument(
                "--mode", choices=MODES, default=DEFAULT_MODE, help="what to generate (default: docstrings)"
            )
            sub.add_argument("--out", default=bench.DEFAULT_OUT, help="folder for the result files")
            sub.add_argument("--config", type=Path, default="momus.toml", help="config file")
            sub.add_argument(
                "--notes",
                default="",
                help="free text saved with the conditions, e.g. what was closed or running",
            )
            sub.add_argument(
                "--review",
                action="store_true",
                help="also send what each model wrote to the reviewer of the [review] settings "
                "and count what it flags (uses the strong model, so it costs its tokens)",
            )
            sub.add_argument(
                "--keep-loaded",
                action="store_true",
                help="do not unload models before each run (the first request then may be warm)",
            )
    return parser


# Run Clio on `files`; show a diff, and write only if `write` is true.
#
# Returns 0 if every file could be read and processed, 1 otherwise.
def comment_command(
    files: list[Path],
    backend: Backend,
    write: bool,
    mode: str = DEFAULT_MODE,
    out=None,
    ledger: Ledger | None = None,
) -> int:
    out = out or sys.stdout
    status = 0
    for path in files:
        try:
            source = read_text_exact(path)
        except (OSError, ClioError) as exc:
            print(f"{path}: cannot read: {exc}", file=sys.stderr)
            status = 1
            continue
        result = comment_source(source, backend, mode)
        if ledger is not None:
            for call in result.calls:
                ledger.record(
                    "clio",
                    getattr(backend, "model", "") or "unknown",
                    call.kind,
                    call.prompt_tokens,
                    call.completion_tokens,
                    call.seconds,
                    added=call.added,
                    rejected=call.rejected,
                    failed=call.failed,
                    dry_run=not write,
                )
        for outcome in result.outcomes:
            print(f"{path}: {outcome.name}: {outcome.status} - {outcome.reason}", file=out)
        if not result.changed:
            continue
        diff = difflib.unified_diff(
            source.splitlines(keepends=True),
            result.text.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
        out.writelines(diff)
        if write:
            write_text_atomic(path, result.text)
            print(f"{path}: written", file=out)
        else:
            print(f"{path}: dry run, nothing written (use --write)", file=out)
    return status


# Checks that each of `files` is its text at `base` plus comments only. A file
# passes when both Argus checks accept it: the code is the same, and the only
# difference is added lines holding comments or docstrings. So a reformatted
# file, or one where an existing comment was edited or removed, is rejected
# too, with a reason that says the code is the same. With `code_only` the
# first check alone decides, and those files pass. Prints one line per file
# and never writes anything. Returns 0 if every file passed, and 1 if any was
# rejected or could not be checked (unreadable, or no baseline in git).
def guard_command(
    files: list[Path],
    base: str = "HEAD",
    read_baseline=read_git_baseline,
    out=None,
    code_only: bool = False,
) -> int:
    out = out or sys.stdout
    status = 0
    for path in files:
        try:
            original, new = read_baseline(path, base), read_text_exact(path)
        except (OSError, ClioError, CriticError) as exc:
            print(f"{path}: cannot check: {exc}", file=sys.stderr)
            status = 1
            continue
        # Asked first so the answer says whether the code itself changed.
        verdict = argus.compare_code(original, new)
        if not verdict.accepted:
            print(f"{path}: REJECTED - {verdict.reason}", file=out)
            status = 1
            continue
        if code_only:
            print(f"{path}: ok - {verdict.reason}", file=out)
            continue
        try:
            added = find_comments(str(path), original, new)
        except CriticError as exc:
            print(f"{path}: REJECTED - same code, but {exc}", file=out)
            status = 1
            continue
        docstrings = sum(comment.kind == "docstring" for comment in added)
        print(
            f"{path}: ok - {docstrings} docstring(s) and {len(added) - docstrings} comment(s) added",
            file=out,
        )
    return status


# Review the comments added to `files` since `base`.
#
# Prints one `file:line: problem` per bad comment and nothing else on
# standard output. With `drop` the flagged comments are then removed from
# the files, each file being written only if the result still passes the
# guard. Short files go to `small_backend` when one is given. Returns 0 if
# every file was reviewed (whether or not problems were found) and 1 if some
# file or request could not be.
def review_command(
    files: list[Path],
    backend: Backend,
    base: str = "HEAD",
    max_items: int = 10,
    read_baseline=read_git_baseline,
    out=None,
    drop: bool = False,
    small_backend: Backend | None = None,
    small_file_lines: int = 0,
    ledger: Ledger | None = None,
) -> int:
    out = out or sys.stdout
    status = 0
    changes = []
    for path in files:
        try:
            changes.append((str(path), read_baseline(path, base), read_text_exact(path)))
        except (OSError, ClioError, CriticError) as exc:
            print(f"{path}: cannot review: {exc}", file=sys.stderr)
            status = 1
    result = review_routed(changes, backend, small_backend, small_file_lines, max_items)
    if ledger is not None:
        for call in result.calls:
            ledger.record(
                "review",
                call["model"],
                "review",
                call["prompt_tokens"],
                call["completion_tokens"],
                call["seconds"],
                reviewed=call["reviewed"],
                flagged=call["flagged"],
                failed=call["failed"],
            )
    for finding in result.findings:
        print(finding, file=out)
    for error in result.errors:
        print(f"momus review: {error}", file=sys.stderr)
    if drop:
        for path, original, new in changes:
            flagged = [finding for finding in result.findings if finding.path == path]
            if not flagged:
                continue
            try:
                write_text_atomic(Path(path), drop_flagged(path, original, new, flagged))
            except (OSError, CriticError) as exc:
                print(f"{path}: nothing removed: {exc}", file=sys.stderr)
                status = 1
            else:
                print(f"{path}: removed {len(flagged)} flagged comment(s)", file=sys.stderr)
    if not result.reviewed and not result.errors and status == 0:
        print("momus review: no added comments to review", file=sys.stderr)
    return 1 if result.errors else status


# Run the CLI and return the process exit status.
#
# With no command it prints the help text and returns 0. Otherwise it
# returns the status of the command that ran.
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "comment":
        files = args.files
        if not files:
            try:
                files = changed_python_files()
            except ClioError as exc:
                print(f"momus comment: cannot list the changed files: {exc}", file=sys.stderr)
                return 1
            if not files:
                print("momus comment: no Python file changed or created since the last commit", file=sys.stderr)
                return 0
            # Shown relative to where the command runs, like the names git prints.
            files = [Path(os.path.relpath(path)) for path in files]
        try:
            settings = load_local_settings(args.config)
            if args.model:
                settings = replace(settings, model=args.model)
            backend = build_local_backend(settings)
        except BackendError as exc:
            print(f"momus comment: {exc}", file=sys.stderr)
            return 1
        return comment_command(files, backend, args.write, args.mode, ledger=Ledger())
    if args.command == "guard":
        return guard_command(args.files, args.base, code_only=args.code_only)
    if args.command == "review":
        try:
            settings = load_review_settings(args.config)
            backend = build_review_backend(settings)
            small_backend = build_small_review_backend(settings)
        except BackendError as exc:
            print(f"momus review: {exc}", file=sys.stderr)
            return 1
        return review_command(
            args.files,
            backend,
            args.base,
            settings.max_items,
            drop=args.drop,
            small_backend=small_backend,
            small_file_lines=settings.small_file_lines,
            ledger=Ledger(),
        )
    return bench.main(args)


if __name__ == "__main__":
    sys.exit(main())
