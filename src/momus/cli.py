"""Command-line entry point for Momus.

``comment`` is implemented (docstrings only for now). The other subcommands
are placeholders that report they are not implemented and exit with a
non-zero status, so nothing can be mistaken for working behaviour.
"""

import argparse
import difflib
import sys
from dataclasses import replace
from pathlib import Path

from momus.backends import Backend, BackendError
from momus.clio import ClioError, comment_source, read_text_exact, write_text_atomic
from momus.config import build_local_backend, load_local_settings

# Subcommand name -> one-line help. The stages behind them are built in later
# plan phases (Clio, Argus, the critic, the benchmark).
COMMANDS = {
    "comment": "add comments and docstrings with the local model (Clio)",
    "guard": "check that code is unchanged apart from comments (Argus)",
    "review": "review comments with the strong model (Momus)",
    "bench": "benchmark the local models",
}


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with one placeholder subcommand per stage."""
    parser = argparse.ArgumentParser(
        prog="momus",
        description="Comment and document freshly written code with few tokens.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    for name, help_text in COMMANDS.items():
        sub = subparsers.add_parser(name, help=help_text, description=help_text)
        if name == "comment":
            sub.add_argument("files", nargs="+", type=Path, help="Python files to document")
            sub.add_argument(
                "--write",
                action="store_true",
                help="write the changes to the files (default: only show the diff)",
            )
            sub.add_argument("--model", help="model to use instead of the one in momus.toml")
            sub.add_argument("--config", type=Path, default="momus.toml", help="config file")
    return parser


def comment_command(files: list[Path], backend: Backend, write: bool, out=None) -> int:
    """Run Clio on ``files``; show a diff, and write only if ``write`` is true.

    Returns 0 if every file could be read and processed, 1 otherwise.
    """
    out = out or sys.stdout
    status = 0
    for path in files:
        try:
            source = read_text_exact(path)
        except (OSError, ClioError) as exc:
            print(f"{path}: cannot read: {exc}", file=sys.stderr)
            status = 1
            continue
        result = comment_source(source, backend)
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


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the process exit status.

    With no command it prints the help text and returns 0. A known command
    returns 1 because none of them is implemented yet; ``comment`` runs Clio.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "comment":
        try:
            settings = load_local_settings(args.config)
            if args.model:
                settings = replace(settings, model=args.model)
            backend = build_local_backend(settings)
        except BackendError as exc:
            print(f"momus comment: {exc}", file=sys.stderr)
            return 1
        return comment_command(args.files, backend, args.write)
    print(f"momus {args.command}: not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
