# Tests for backups and `momus restore` (plan §16.7). No model is used, and
# the copies always go to a temporary state folder (see conftest.py).

import io
import json
import subprocess

import pytest

from momus import cli
from momus.backends.fake import FakeBackend
from momus.backup import BackupError, Backups, text_hash
from momus.cli import build_parser, comment_command, restore_command, review_command

ORIGINAL = '"""Shapes."""\n\ndef area(side):\n    return side * side\n'
WRITTEN = '"""Shapes."""\n\ndef area(side):\n    """Return the area of a square."""\n    return side * side\n'
DOC = "DOCSTRING:\nReturn the area of a square."


def source_file(tmp_path, text=ORIGINAL, name="shop/geometry.py"):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def write_with_clio(path, backups, reply=DOC):
    return comment_command([path], FakeBackend([reply]), write=True, out=io.StringIO(), backups=backups)


# --- Saving copies ----------------------------------------------------------


@pytest.mark.parametrize("text", [ORIGINAL, "x = 1\r\ny = 2\r\n", "x = 'caffè'", ""])
def test_a_copy_holds_the_text_exactly(tmp_path, text):
    path = source_file(tmp_path, text)
    version = Backups().save(path, text, text + "# more\n")
    assert version.read() == text
    assert version.text_path.read_bytes() == text.encode()
    assert (version.original_sha256, version.written_sha256) == (text_hash(text), text_hash(text + "# more\n"))


def test_copies_live_in_the_state_folder_of_the_project_not_in_the_project(tmp_path, state_home):
    path = source_file(tmp_path)
    before = sorted(p.name for p in path.parent.iterdir())
    version = Backups().save(path, ORIGINAL, WRITTEN)
    assert state_home / "shop" / "backups" in version.text_path.parents
    assert sorted(p.name for p in path.parent.iterdir()) == before
    facts = json.loads(version.facts_path.read_text())
    assert facts["path"] == "geometry.py"  # inside the project: no machine path
    assert str(tmp_path) not in version.facts_path.read_text()


def test_only_the_last_copies_are_kept(tmp_path):
    path = source_file(tmp_path)
    backups = Backups(keep=3)
    for number in range(5):
        backups.save(path, f"x = {number}\n", "y\n")
    kept = backups.versions(path)
    assert [version.number for version in kept] == [3, 4, 5]
    assert kept[-1].read() == "x = 4\n"
    assert len(list(kept[0].text_path.parent.iterdir())) == 6  # three texts, three fact files


def test_files_with_the_same_name_in_different_folders_do_not_share_copies(tmp_path):
    first = source_file(tmp_path, name="shop/a/util.py")
    second = source_file(tmp_path, name="shop/b/util.py")
    # One git repository holds both, so they are files of the same project.
    subprocess.run(["git", "-C", str(tmp_path / "shop"), "init", "-q"], check=True, capture_output=True)
    backups = Backups()
    backups.save(first, "first\n", "x\n")
    assert backups.versions(second) == []
    assert len(backups.versions(first)) == 1
    facts = json.loads(backups.versions(first)[0].facts_path.read_text())
    assert facts["path"] == "a/util.py"


def test_a_damaged_or_unfinished_copy_is_not_used(tmp_path):
    path = source_file(tmp_path)
    backups = Backups()
    version = backups.save(path, ORIGINAL, WRITTEN)
    version.text_path.write_text("something else")
    with pytest.raises(BackupError, match="damaged"):
        version.read()
    version.facts_path.unlink()  # a copy whose facts were never written
    assert backups.versions(path) == []


def test_a_copy_that_cannot_be_saved_is_an_error(tmp_path, monkeypatch):
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the state folder should be")
    monkeypatch.setenv("XDG_STATE_HOME", str(blocked))
    with pytest.raises(BackupError):
        Backups().save(source_file(tmp_path), ORIGINAL, WRITTEN)


# --- Writing saves a copy first ---------------------------------------------


def test_writing_saves_the_original_first(tmp_path):
    path = source_file(tmp_path)
    backups = Backups()
    assert write_with_clio(path, backups) == 0
    assert path.read_text() == WRITTEN
    (version,) = backups.versions(path)
    assert version.read() == ORIGINAL and version.written_sha256 == text_hash(WRITTEN)


def test_no_copy_means_no_write(tmp_path, monkeypatch, capsys):
    path = source_file(tmp_path)
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the state folder should be")
    monkeypatch.setenv("XDG_STATE_HOME", str(blocked))
    assert write_with_clio(path, Backups()) == 1
    assert path.read_text() == ORIGINAL
    assert "not written: no backup could be saved" in capsys.readouterr().err


def test_a_dry_run_saves_no_copy(tmp_path, state_home):
    path = source_file(tmp_path)
    backups = Backups()
    assert comment_command([path], FakeBackend([DOC]), write=False, out=io.StringIO(), backups=backups) == 0
    assert backups.versions(path) == [] and not state_home.exists()


def test_dropping_flagged_comments_saves_a_copy_too(tmp_path):
    path = source_file(tmp_path, WRITTEN)
    backups = Backups()
    status = review_command(
        [path], FakeBackend(["C1: Wrong."]), read_baseline=lambda p, ref: ORIGINAL,
        out=io.StringIO(), drop=True, backups=backups,
    )
    assert status == 0 and path.read_text() == ORIGINAL
    assert backups.versions(path)[0].read() == WRITTEN
    assert restore_command([path], backups, out=io.StringIO()) == 0
    assert path.read_text() == WRITTEN  # the dropped comment is back


# --- Restoring ---------------------------------------------------------------


def test_restore_puts_back_the_exact_original_and_uses_up_the_copy(tmp_path):
    original = ORIGINAL.replace("\n", "\r\n")
    path = source_file(tmp_path, original)
    backups = Backups()
    assert write_with_clio(path, backups) == 0 and path.read_bytes() != original.encode()
    out = io.StringIO()
    assert restore_command([path], backups, out=out) == 0
    assert path.read_bytes() == original.encode() and "restored" in out.getvalue()
    assert backups.versions(path) == []


def test_restoring_twice_goes_back_two_writes(tmp_path):
    path = source_file(tmp_path, "def a():\n    return 1\n")
    backups = Backups()
    first = path.read_text()
    assert write_with_clio(path, backups, "DOCSTRING:\nReturn one.") == 0
    second = path.read_text()
    path.write_text(second.replace('"""Return one."""\n', ""))  # the function's docstring is removed by hand
    middle = path.read_text()
    assert write_with_clio(path, backups, "DOCSTRING:\nGive one.") == 0
    assert len(backups.versions(path)) == 2
    assert restore_command([path], backups, out=io.StringIO()) == 0 and path.read_text() == middle
    # The older copy belongs to a text that is no longer on disk: refused.
    assert restore_command([path], backups, out=io.StringIO()) == 1 and path.read_text() == middle
    assert restore_command([path], backups, force=True, out=io.StringIO()) == 0
    assert path.read_text() == first


def test_restore_refuses_a_file_edited_since_unless_forced(tmp_path, capsys):
    path = source_file(tmp_path)
    backups = Backups()
    write_with_clio(path, backups)
    edited = path.read_text().replace("Return the area", "Give the area")
    path.write_text(edited)
    assert restore_command([path], backups, out=io.StringIO()) == 1
    assert path.read_text() == edited and "edited after Momus wrote it" in capsys.readouterr().err
    assert len(backups.versions(path)) == 1  # the copy is still there
    assert restore_command([path], backups, force=True, out=io.StringIO()) == 0
    assert path.read_text() == ORIGINAL


def test_restore_never_undoes_a_change_to_the_code_even_when_forced(tmp_path, capsys):
    path = source_file(tmp_path)
    backups = Backups()
    write_with_clio(path, backups)
    edited = path.read_text().replace("side * side", "side ** 2")
    path.write_text(edited)
    for force in (False, True):
        assert restore_command([path], backups, force=force, out=io.StringIO()) == 1
        assert path.read_text() == edited
    err = capsys.readouterr().err
    (version,) = backups.versions(path)
    assert "the code changed since the backup" in err and str(version.text_path) in err


def test_restore_without_a_copy_or_without_the_file_fails_cleanly(tmp_path, capsys):
    path = source_file(tmp_path)
    backups = Backups()
    assert restore_command([path], backups, out=io.StringIO()) == 1
    assert "no backup to restore" in capsys.readouterr().err
    write_with_clio(path, backups)
    path.unlink()
    assert restore_command([path], backups, out=io.StringIO()) == 1
    assert "not restored" in capsys.readouterr().err


def test_restore_of_a_file_that_was_never_written_says_so(tmp_path):
    path = source_file(tmp_path)
    backups = Backups()
    backups.save(path, ORIGINAL, WRITTEN)  # the copy was made, the write never happened
    out = io.StringIO()
    assert restore_command([path], backups, out=out) == 0
    assert "already as it was" in out.getvalue() and path.read_text() == ORIGINAL
    assert backups.versions(path) == []


def test_a_damaged_copy_is_not_restored(tmp_path, capsys):
    path = source_file(tmp_path)
    backups = Backups()
    write_with_clio(path, backups)
    backups.versions(path)[0].text_path.write_text("something else")
    assert restore_command([path], backups, out=io.StringIO()) == 1
    assert path.read_text() == WRITTEN and "damaged" in capsys.readouterr().err


# --- Command line ------------------------------------------------------------


def test_restore_options_are_parsed():
    args = build_parser().parse_args(["restore", "a.py", "b.py", "--force"])
    assert [str(f) for f in args.files] == ["a.py", "b.py"] and args.force is True
    assert build_parser().parse_args(["restore", "a.py"]).force is False


def test_the_command_line_backs_up_on_write_and_restores(tmp_path, monkeypatch, capsys):
    path = source_file(tmp_path)
    monkeypatch.setattr(cli, "build_local_backend", lambda settings: FakeBackend([DOC]))
    monkeypatch.chdir(path.parent)
    assert cli.main(["comment", "geometry.py", "--write", "--config", "absent.toml"]) == 0
    assert path.read_text() == WRITTEN
    assert cli.main(["restore", "geometry.py"]) == 0
    assert path.read_text() == ORIGINAL
    assert cli.main(["restore", "geometry.py"]) == 1  # nothing left to restore
