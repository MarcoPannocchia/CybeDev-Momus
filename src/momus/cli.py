"""Command-line entry point for Momus.

Only the command skeleton exists for now: every subcommand is a placeholder
that reports it is not implemented and exits with a non-zero status, so
nothing can be mistaken for working behaviour.
"""

import argparse
import sys

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
        subparsers.add_parser(name, help=help_text, description=help_text)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the process exit status.

    With no command it prints the help text and returns 0. A known command
    returns 1 because none of them is implemented yet.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    print(f"momus {args.command}: not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
