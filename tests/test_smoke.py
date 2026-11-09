"""Smoke tests: the package imports and the CLI skeleton responds."""

import pytest

import momus
from momus.cli import COMMANDS, main


def test_package_imports():
    assert momus.__doc__


def test_no_command_prints_help_and_succeeds(capsys):
    assert main([]) == 0
    assert "usage: momus" in capsys.readouterr().out


def test_help_flag_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    for name in COMMANDS:
        assert name in out


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_placeholder_commands_report_not_implemented(command, capsys):
    assert main([command]) == 1
    assert "not implemented yet" in capsys.readouterr().err
