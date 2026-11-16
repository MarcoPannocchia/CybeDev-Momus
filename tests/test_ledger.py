# Tests for the usage ledger (plan §11, §16.10). No model is used, and the
# ledger is always in a temporary state folder (see conftest.py).

import io
import json
import subprocess

import pytest

from momus import cli, clio, critic, ledger
from momus.backends import BackendError
from momus.backends.fake import FakeBackend
from momus.cli import comment_command, review_command
from momus.ledger import Ledger

FIELDS = {
    "time", "project", "run", "stage", "model", "kind", "prompt_tokens", "completion_tokens",
    "seconds", "added", "rejected", "reviewed", "flagged", "failed", "dry_run",
}
SOURCE = '"""Shapes."""\n\ndef area(side):\n    return side * side\n'


# A fake with a name and token counts, like a real backend has.
class Counted(FakeBackend):
    model = "tiny-model"

    def complete(self, prompt):
        self.last_usage = {"prompt_tokens": 40, "completion_tokens": 7}
        return super().complete(prompt)


def project(tmp_path, name="shop"):
    root = tmp_path / name
    root.mkdir(parents=True)
    return root


# --- Where the file lives ---------------------------------------------------


def test_the_state_folder_follows_xdg_and_ignores_a_relative_value(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert ledger.state_home() == tmp_path / "state" / "momus"
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for value in ("relative/state", ""):
        monkeypatch.setenv("XDG_STATE_HOME", value)
        assert ledger.state_home() == tmp_path / "home" / ".local" / "state" / "momus"


def test_the_project_is_the_git_repository_or_else_the_folder(tmp_path):
    root = project(tmp_path)
    (root / "pkg").mkdir()
    assert ledger.project_root(root / "pkg") == root / "pkg"
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    assert ledger.project_root(root / "pkg") == root


def test_records_go_to_a_folder_named_after_the_project(tmp_path, state_home):
    book = Ledger(project(tmp_path))
    assert book.record("clio", "m") is True
    assert book.path == state_home / "shop" / "usage.jsonl" and book.path.exists()
    assert book.project == "shop"


def test_two_projects_with_the_same_folder_name_are_kept_apart(tmp_path, state_home):
    first, second = Ledger(project(tmp_path / "a")), Ledger(project(tmp_path / "b"))
    assert first.record("clio", "m") and second.record("clio", "m")
    assert first.project == "shop"
    assert second.project.startswith("shop-") and len(second.project) == len("shop-") + 4
    assert first.path != second.path and first.path.exists() and second.path.exists()
    # Each finds its own folder again, and the name without a suffix is not stolen.
    assert Ledger(tmp_path / "a" / "shop").path == first.path
    assert Ledger(tmp_path / "b" / "shop").path == second.path
    # The path of the project is written nowhere.
    stored = "".join(p.read_text() for p in state_home.rglob("*") if p.is_file())
    assert str(tmp_path) not in stored


# --- What a record holds ----------------------------------------------------


def test_a_record_is_one_json_line_with_fixed_fields(tmp_path):
    book = Ledger(project(tmp_path))
    book.record("clio", "m1", "docstring", 40, 7, 1.23456, added=1, dry_run=True)
    book.record("review", "m2", "review", reviewed=3, flagged=1)
    first, second = ledger.read_records(book.path)
    assert set(first) == FIELDS and set(second) == FIELDS
    assert (first["stage"], first["model"], first["kind"]) == ("clio", "m1", "docstring")
    assert (first["prompt_tokens"], first["completion_tokens"], first["seconds"]) == (40, 7, 1.235)
    assert (first["added"], first["dry_run"], first["failed"]) == (1, True, False)
    assert (second["reviewed"], second["flagged"], second["dry_run"]) == (3, 1, None)
    assert first["run"] == second["run"] and first["time"].endswith("+00:00")
    assert len(book.path.read_text().splitlines()) == 2


def test_token_counts_that_are_not_numbers_are_left_empty(tmp_path):
    book = Ledger(project(tmp_path))
    book.record("clio", "m", prompt_tokens="def secret(): pass", completion_tokens=True)
    (entry,) = ledger.read_records(book.path)
    assert entry["prompt_tokens"] is None and entry["completion_tokens"] is None
    assert "secret" not in book.path.read_text()


def test_there_is_no_way_to_pass_free_text(tmp_path):
    with pytest.raises(TypeError):
        Ledger(project(tmp_path)).record("clio", "m", note="def secret(): pass")


def test_a_ledger_that_cannot_be_written_never_fails_the_run(tmp_path, monkeypatch):
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the state folder should be")
    monkeypatch.setenv("XDG_STATE_HOME", str(blocked))
    book = Ledger(project(tmp_path))
    assert book.record("clio", "m") is False
    assert book.record("clio", "m", seconds="soon") is False  # bad input does not raise either


def test_reading_skips_what_is_not_a_record(tmp_path):
    path = tmp_path / "usage.jsonl"
    path.write_text('{"stage": "clio"}\nnot json\n[1, 2]\n\n{"stage": "review"}\n')
    assert [entry["stage"] for entry in ledger.read_records(path)] == ["clio", "review"]
    assert ledger.read_records(tmp_path / "missing.jsonl") == []


# --- Clio reports each request in numbers -----------------------------------


def test_clio_reports_one_call_per_request_with_tokens_and_what_came_of_it():
    source = "def a():\n    return 1\n\ndef b():\n    return 2\n"
    backend = Counted(["DOCSTRING:\nReturn one.", "no marker", "DOCSTRING:\nNumbers."])
    result = clio.comment_source(source, backend)
    assert [(c.kind, c.added, c.rejected, c.failed) for c in result.calls] == [
        ("docstring", 1, 0, False),
        ("docstring", 0, 1, False),
        ("docstring", 1, 0, False),
    ]
    assert all((c.prompt_tokens, c.completion_tokens) == (40, 7) and c.seconds >= 0 for c in result.calls)


def test_a_comment_request_counts_every_comment_it_led_to():
    source = (
        '"""Mod."""\n\ndef f(a):\n    """Doc."""\n    b = a + 1\n    c = b * 2\n    d = c - 3\n    return d\n'
    )
    reply = "COMMENTS:\nS2: Doubled because sizes come in halves.\nS9: Not a statement."
    result = clio.comment_source(source, FakeBackend([reply]), "comments")
    (call,) = result.calls
    assert (call.kind, call.added, call.rejected) == ("comment", 1, 1)
    assert call.prompt_tokens is None  # this fake reports no usage


def test_a_request_the_server_did_not_answer_is_a_failed_call():
    class Down:
        def complete(self, prompt):
            raise BackendError("server is down")

    result = clio.comment_source("def a():\n    return 1\n", Down())
    assert [(c.failed, c.added, c.rejected) for c in result.calls] == [(True, 0, 1), (True, 0, 1)]


# --- The commands write the ledger ------------------------------------------


def test_momus_comment_records_each_request_and_no_code(tmp_path):
    root = project(tmp_path)
    path = root / "geometry.py"
    path.write_text(SOURCE)
    book = Ledger(root)
    backend = Counted(["DOCSTRING:\nReturn the area of a square."])
    assert comment_command([path], backend, write=False, out=io.StringIO(), ledger=book) == 0
    (entry,) = ledger.read_records(book.path)
    assert (entry["stage"], entry["model"], entry["kind"]) == ("clio", "tiny-model", "docstring")
    assert (entry["prompt_tokens"], entry["completion_tokens"], entry["added"]) == (40, 7, 1)
    assert entry["dry_run"] is True
    text = book.path.read_text()
    for leak in ("def area", "side * side", "Return the area", "geometry", "Shapes"):
        assert leak not in text
    assert comment_command([path], backend, write=True, out=io.StringIO(), ledger=book) == 0
    assert ledger.read_records(book.path)[-1]["dry_run"] is False


def test_momus_comment_without_a_ledger_writes_none(tmp_path, state_home):
    path = project(tmp_path) / "geometry.py"
    path.write_text(SOURCE)
    assert comment_command([path], Counted(["DOCSTRING:\nDoc."]), write=False, out=io.StringIO()) == 0
    assert not state_home.exists()


def test_momus_review_records_each_request(tmp_path):
    root = project(tmp_path)
    path = root / "geometry.py"
    new = SOURCE.replace("    return", '    """Return the perimeter."""\n    return')
    path.write_text(new)
    book = Ledger(root)
    backend = Counted(["C1: It returns the area, not the perimeter."])
    status = review_command(
        [path], backend, read_baseline=lambda p, ref: SOURCE, out=io.StringIO(), ledger=book
    )
    assert status == 0
    (entry,) = ledger.read_records(book.path)
    assert (entry["stage"], entry["model"]) == ("review", "tiny-model")
    assert (entry["reviewed"], entry["flagged"], entry["failed"]) == (1, 1, False)
    assert (entry["prompt_tokens"], entry["completion_tokens"]) == (40, 7)
    assert "perimeter" not in book.path.read_text()


def test_a_review_request_that_fails_is_recorded_as_failed():
    new = SOURCE.replace("    return", '    """Doc."""\n    return')
    result = critic.review_changes([("m.py", SOURCE, new)], Counted(["I liked it."]))
    (call,) = result.calls
    assert (call["failed"], call["reviewed"], call["flagged"]) == (True, 0, 0)
    assert call["prompt_tokens"] == 40  # the tokens were spent all the same


def test_the_review_calls_of_both_models_are_kept(tmp_path):
    long_new = SOURCE.replace("    return", '    """Doc."""\n    return') + "\n" * 300
    short_new = SOURCE.replace("    return", '    """Doc."""\n    return')
    big, small = Counted(["OK"]), Counted(["OK"])
    small.model = "small-model"
    changes = [("long.py", SOURCE + "\n" * 300, long_new), ("short.py", SOURCE, short_new)]
    result = critic.review_routed(changes, big, small, small_file_lines=200)
    assert sorted(call["model"] for call in result.calls) == ["small-model", "tiny-model"]


def test_the_command_line_writes_to_the_state_folder_of_the_project(tmp_path, state_home, monkeypatch, capsys):
    root = project(tmp_path)
    (root / "geometry.py").write_text(SOURCE)
    monkeypatch.setattr(cli, "build_local_backend", lambda settings: Counted(["DOCSTRING:\nDoc."]))
    monkeypatch.chdir(root)
    assert cli.main(["comment", "geometry.py", "--config", "absent.toml"]) == 0
    (entry,) = ledger.read_records(state_home / "shop" / "usage.jsonl")
    assert entry["project"] == "shop" and entry["stage"] == "clio"
