# Tests for the ownership record (plan §16.7): which comments Momus wrote. No
# model is used, and the record is always in a temporary state folder.

import io
import json

import pytest

from momus import cli
from momus.backends.fake import FakeBackend
from momus.cli import build_parser, comment_command, review_command
from momus.ownership import Ownership, comment_hash

ORIGINAL = "def area(side):\n    return side * side\n\n\nclass Box:\n    def grow(self):\n        self.size = 2\n"
DOC = "DOCSTRING:\nDoc."


# Let Clio (a fake) write docstrings into a new file, as `momus comment --write` does.
def written_file(tmp_path, source=ORIGINAL, ownership=None, reply=DOC):
    path = tmp_path / "shop" / "geometry.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    ownership = ownership or Ownership()
    assert comment_command([path], FakeBackend([reply]), True, out=io.StringIO(), ownership=ownership) == 0
    return path, ownership


def owned_texts(ownership, path, original=ORIGINAL):
    new = path.read_text()
    lines = new.splitlines()
    return sorted(lines[first - 1].strip() for first, _ in ownership.select(path, original, new))


def review(path, backend, original=ORIGINAL, **options):
    out = io.StringIO()
    status = review_command([path], backend, read_baseline=lambda p, ref: original, out=out, **options)
    return status, out.getvalue()


# --- Recognising a comment --------------------------------------------------


def test_the_hash_ignores_indentation_and_nothing_else():
    assert comment_hash("Return one.\n\n    Args:\n        a: it") == comment_hash("  Return one.\n\nArgs:\n  a: it  ")
    assert comment_hash("Return one.") != comment_hash("Return two.")
    assert comment_hash("Return one.") != comment_hash("return one.")


def test_what_momus_writes_is_recorded_by_file_kind_name_and_hash(tmp_path, state_home):
    path, _ = written_file(tmp_path)
    record = state_home / "shop" / "comments.jsonl"
    entries = [json.loads(line) for line in record.read_text().splitlines()]
    assert {(e["event"], e["file"], e["kind"], e["name"]) for e in entries} == {
        ("written", "geometry.py", "docstring", "<module>"),
        ("written", "geometry.py", "docstring", "area"),
        ("written", "geometry.py", "docstring", "Box"),
        ("written", "geometry.py", "docstring", "Box.grow"),
    }
    assert all(len(e["hash"]) == 64 and set(e) == {"time", "event", "file", "kind", "name", "hash"} for e in entries)
    # Locations and hashes only: no comment text, no code, no machine path.
    text = record.read_text()
    assert "Doc." not in text and "side * side" not in text and str(tmp_path) not in text


def test_a_dry_run_records_nothing(tmp_path, state_home):
    path = tmp_path / "geometry.py"
    path.write_text(ORIGINAL)
    assert comment_command([path], FakeBackend([DOC]), False, out=io.StringIO(), ownership=Ownership()) == 0
    assert not state_home.exists()


def test_inline_comments_are_recorded_under_the_function_they_are_in(tmp_path, state_home):
    source = '"""Mod."""\n\ndef f(a):\n    """Doc."""\n    b = a + 1\n    c = b * 2\n    d = c - 3\n    return d\n'
    path = tmp_path / "shop" / "m.py"
    path.parent.mkdir()
    path.write_text(source)
    backend = FakeBackend(["COMMENTS:\nS2: Doubled because sizes come in halves."])
    ownership = Ownership()
    assert comment_command([path], backend, True, mode="comments", out=io.StringIO(), ownership=ownership) == 0
    (entry,) = [json.loads(line) for line in (state_home / "shop" / "comments.jsonl").read_text().splitlines()]
    assert (entry["kind"], entry["name"]) == ("comment", "f")
    assert owned_texts(ownership, path, source) == ["# Doubled because sizes come in halves."]


# --- What counts as Momus's own ---------------------------------------------


def test_only_what_momus_wrote_is_its_own(tmp_path):
    path, ownership = written_file(tmp_path)
    assert owned_texts(ownership, path) == ['"""Doc."""'] * 4
    # The maintainer adds a comment and a docstring-less function gets one by hand.
    text = path.read_text().replace("    return side * side", "    # Squares only.\n    return side * side")
    path.write_text(text)
    assert "# Squares only." not in owned_texts(ownership, path)
    assert len(owned_texts(ownership, path)) == 4


def test_a_comment_keeps_its_owner_when_lines_move(tmp_path):
    path, ownership = written_file(tmp_path)
    # Code is added above every definition: all their line numbers change.
    moved = path.read_text().replace("def area", "import os\n\n\ndef area")
    path.write_text(moved)
    assert len(ownership.select(path, "import os\n\n\n" + ORIGINAL, moved)) == 4


def test_an_edited_comment_is_no_longer_momus_s(tmp_path):
    path, ownership = written_file(tmp_path, reply="DOCSTRING:\nReturn the area.")
    text = path.read_text()
    assert len(ownership.select(path, ORIGINAL, text)) == 4
    edited = text.replace('    """Return the area."""\n    return side', '    """Return the area of a square."""\n    return side')
    assert edited != text
    path.write_text(edited)
    assert len(ownership.select(path, ORIGINAL, edited)) == 3


def test_a_renamed_function_takes_its_comment_out_of_momus_s_hands(tmp_path):
    path, ownership = written_file(tmp_path)
    renamed_original = ORIGINAL.replace("def area", "def surface")
    renamed = path.read_text().replace("def area", "def surface")
    assert len(ownership.select(path, renamed_original, renamed)) == 3


def test_the_same_words_in_another_function_are_not_owned(tmp_path):
    path, ownership = written_file(tmp_path)
    original = ORIGINAL + "\n\ndef volume(side):\n    return side ** 3\n"
    new = path.read_text() + '\n\ndef volume(side):\n    """Doc."""\n    return side ** 3\n'
    selected = ownership.select(path, original, new)
    assert len(selected) == 4 and not any(first > 15 for first, _ in selected)


def test_a_lost_record_means_nothing_is_owned(tmp_path, state_home):
    path, ownership = written_file(tmp_path)
    (state_home / "shop" / "comments.jsonl").unlink()
    assert ownership.select(path, ORIGINAL, path.read_text()) == set()


def test_a_change_to_the_code_means_nothing_can_be_established(tmp_path):
    path, ownership = written_file(tmp_path)
    assert ownership.select(path, ORIGINAL, path.read_text().replace("side * side", "side + side")) == set()


def test_a_record_that_cannot_be_written_never_fails_the_run(tmp_path, monkeypatch):
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the state folder should be")
    monkeypatch.setenv("XDG_STATE_HOME", str(blocked))
    path, ownership = written_file(tmp_path)  # the write itself succeeds
    assert '"""Doc."""' in path.read_text()
    assert ownership.record_written(path, ORIGINAL, path.read_text()) == 0
    assert ownership.select(path, ORIGINAL, path.read_text()) == set()


# --- Reviewing only Momus's comments ----------------------------------------


def with_a_comment_by_hand(path):
    text = path.read_text().replace("    return side * side", "    # Squares only.\n    return side * side")
    path.write_text(text)
    return text


def test_review_mine_shows_the_reviewer_only_momus_s_comments(tmp_path):
    path, ownership = written_file(tmp_path)
    with_a_comment_by_hand(path)
    backend = FakeBackend(["OK"])
    assert review(path, backend, ownership=ownership, mine=True)[0] == 0
    asked = backend.prompts[0]
    assert asked.count("docstring): ") == 4 and "comment): " not in asked
    everything = FakeBackend(["OK"])
    review(path, everything, ownership=ownership)
    assert "comment): Squares only." in everything.prompts[0]  # without --mine it is reviewed too


def test_drop_with_mine_cannot_remove_a_comment_written_by_hand(tmp_path, capsys):
    path, ownership = written_file(tmp_path)
    with_a_comment_by_hand(path)
    # The reviewer flags everything it is shown, and one number it was not given.
    backend = FakeBackend(["C1: Bad.\nC2: Bad.\nC3: Bad.\nC4: Bad.\nC5: Bad."])
    review(path, backend, ownership=ownership, mine=True, drop=True)
    left = path.read_text()
    assert "# Squares only." in left and '"""Doc."""' not in left
    # The empty line that came with the file's docstring stays behind.
    assert left.replace("    # Squares only.\n", "") == "\n" + ORIGINAL


def test_review_mine_without_a_record_reviews_nothing(tmp_path, capsys):
    path = tmp_path / "shop" / "geometry.py"
    path.parent.mkdir()
    path.write_text(ORIGINAL.replace("    return side", '    """By hand."""\n    return side'))
    backend = FakeBackend(["C1: Bad."])
    status, out = review(path, backend, mine=True, drop=True)
    assert (status, out, backend.prompts) == (0, "", [])
    assert '"""By hand."""' in path.read_text()
    assert "no comments written by Momus to review" in capsys.readouterr().err


def test_unreviewed_skips_what_the_reviewer_has_already_read(tmp_path, state_home):
    path, ownership = written_file(tmp_path)
    first = FakeBackend(["OK"])
    review(path, first, ownership=ownership, unreviewed=True)
    assert len(first.prompts) == 1
    events = [json.loads(line)["event"] for line in (state_home / "shop" / "comments.jsonl").read_text().splitlines()]
    assert events.count("written") == 4 and events.count("reviewed") == 4
    second = FakeBackend(["OK"])
    review(path, second, ownership=ownership, unreviewed=True)
    assert second.prompts == []
    # --mine alone still reviews them again.
    third = FakeBackend(["OK"])
    review(path, third, ownership=ownership, mine=True)
    assert len(third.prompts) == 1


def test_a_review_that_failed_does_not_count_as_read(tmp_path, state_home):
    path, ownership = written_file(tmp_path)
    review(path, FakeBackend(["I liked it."]), ownership=ownership, unreviewed=True)
    again = FakeBackend(["OK"])
    review(path, again, ownership=ownership, unreviewed=True)
    assert len(again.prompts) == 1


# --- Command line -------------------------------------------------------------


def test_review_ownership_options_are_parsed():
    args = build_parser().parse_args(["review", "a.py", "--mine", "--unreviewed"])
    assert args.mine is True and args.unreviewed is True
    plain = build_parser().parse_args(["review", "a.py"])
    assert plain.mine is False and plain.unreviewed is False


def test_the_command_line_records_what_it_writes(tmp_path, state_home, monkeypatch):
    path = tmp_path / "shop" / "geometry.py"
    path.parent.mkdir()
    path.write_text(ORIGINAL)
    monkeypatch.setattr(cli, "build_local_backend", lambda settings: FakeBackend([DOC]))
    monkeypatch.chdir(path.parent)
    assert cli.main(["comment", "geometry.py", "--write", "--config", "absent.toml"]) == 0
    assert len((state_home / "shop" / "comments.jsonl").read_text().splitlines()) == 4
