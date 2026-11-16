# Backups: a copy of every file Momus is about to change, and how to get it back.
#
# Before a file is written, its text as it was goes into the project's state
# folder (see `momus.state`), outside the project. Unlike git, this also
# covers changes that were never committed. `momus restore` puts the latest
# copy back.
#
# Each copy is two files in a folder of its own per source file: the text
# (`000001.orig`) and a few facts about it (`000001.json`): the file's path
# inside the project, the time, and SHA-256 hashes of the text before and
# after Momus wrote. The second hash is how a restore can tell that nobody has
# touched the file since. The facts are written last, so a copy that was cut
# short has none and is ignored.

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from momus.state import claim_project_folder, locate, project_folder

# How many copies of each file are kept. Decided by the maintainer
# (2026-11-12); meant to become a setting.
KEEP = 5


# Raised when a copy cannot be saved or read.
class BackupError(Exception):
    pass


# The hash of a text as it is stored on disk (UTF-8).
def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# One saved copy of a file.
@dataclass(frozen=True)
class Version:
    number: int
    text_path: Path
    facts_path: Path
    original_sha256: str  # the text in the copy
    written_sha256: str  # the text Momus wrote over it

    # Raises:
    #     BackupError: if the copy cannot be read or is not the text that was saved.
    def read(self) -> str:
        try:
            with open(self.text_path, encoding="utf-8", newline="") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise BackupError(f"cannot read the copy: {exc}") from exc
        if text_hash(text) != self.original_sha256:
            raise BackupError("the copy is damaged (its hash does not match)")
        return text


# The copies kept for the files of whatever project each file belongs to.
class Backups:
    def __init__(self, home: Path | None = None, keep: int = KEEP) -> None:
        self.home = home
        self.keep = keep

    # Where the copies of `name` go. The folder is named by a hash, because a
    # path is not a safe folder name.
    def _folder(self, base: Path, name: str) -> Path:
        key = hashlib.sha256(name.encode("utf-8", errors="surrogateescape")).hexdigest()[:16]
        return base / "backups" / key

    # The copies of `path`, oldest first. Copies without their facts, or with
    # facts that cannot be read, are left out.
    def versions(self, path: Path) -> list[Version]:
        root, name = locate(path)
        folder = self._folder(project_folder(root, self.home), name)
        found = []
        for facts_path in sorted(folder.glob("*.json")):
            try:
                facts = json.loads(facts_path.read_text(encoding="utf-8"))
                found.append(
                    Version(
                        int(facts_path.stem),
                        facts_path.with_suffix(".orig"),
                        facts_path,
                        str(facts["original_sha256"]),
                        str(facts["written_sha256"]),
                    )
                )
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(found, key=lambda version: version.number)

    # Save `original`, the text of `path` before `written` replaces it.
    #
    # Raises:
    #     BackupError: if the copy could not be saved. The caller must then
    #         not write the file.
    def save(self, path: Path, original: str, written: str) -> Version:
        try:
            root, name = locate(path)
            folder = self._folder(claim_project_folder(root, self.home), name)
            folder.mkdir(parents=True, exist_ok=True)
            existing = self.versions(path)
            number = existing[-1].number + 1 if existing else 1
            version = Version(
                number,
                folder / f"{number:06d}.orig",
                folder / f"{number:06d}.json",
                text_hash(original),
                text_hash(written),
            )
            with open(version.text_path, "w", encoding="utf-8", newline="") as handle:
                handle.write(original)
            facts = {
                "path": name,
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "original_sha256": version.original_sha256,
                "written_sha256": version.written_sha256,
            }
            version.facts_path.write_text(json.dumps(facts) + "\n", encoding="utf-8")
            # Checked by reading it back: a copy that cannot be read is no copy.
            version.read()
        except (OSError, UnicodeError, ValueError) as exc:
            raise BackupError(str(exc)) from exc
        for old in existing[: max(0, len(existing) + 1 - self.keep)]:
            self.remove(old)
        return version

    # Delete one copy. A copy that cannot be deleted is left where it is.
    def remove(self, version: Version) -> None:
        for file in (version.facts_path, version.text_path):
            try:
                file.unlink()
            except OSError:
                pass
