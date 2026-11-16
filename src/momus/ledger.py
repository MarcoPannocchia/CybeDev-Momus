# The usage ledger: one line per model call, counts and a few names.
#
# Every call Clio or the reviewer makes is recorded as one JSON object on its
# own line: when, which project, which stage and model, the tokens in and out,
# the seconds it took and what came of it (docstrings added, comments flagged).
# A record never holds code, comment text or a file name. It does hold the
# name of the project's folder and of the model, which is worth a look before
# the file is shared.
#
# The file lives outside the projects, in the user's state folder
# (`$XDG_STATE_HOME/momus/<project>/usage.jsonl`, or `~/.local/state/...`), so
# a project's repository and its `.gitignore` are never touched.
#
# Recording must never be able to fail a run: every write swallows its errors
# and reports them with a return value nobody is obliged to read.

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# `state_home` is not used here; it is kept reachable as `ledger.state_home`.
from momus.state import claim_project_folder, project_folder, project_root, state_home

LEDGER_NAME = "usage.jsonl"


# Writes the records of one run of a command for one project.
class Ledger:
    def __init__(self, root: Path | str | None = None, home: Path | None = None) -> None:
        try:
            self.root = project_root(root or ".")
        except Exception:  # an unreadable folder must not stop the command
            self.root = Path(".")
        self.home = home
        now = datetime.now(timezone.utc)
        # One id per command run, so the calls of a run can be added up.
        self.run = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}"

    # Looked up every time and not once at the start: another project with
    # the same folder name may have claimed the plain name in the meantime.
    @property
    def folder(self) -> Path:
        return project_folder(self.root, self.home)

    @property
    def project(self) -> str:
        return self.folder.name

    @property
    def path(self) -> Path:
        return self.folder / LEDGER_NAME

    # Append one record. Returns whether it was written; never raises.
    #
    # Only numbers, true/false and three short names (stage, model, kind) are
    # accepted, which is what keeps code and comment text out of the file.
    def record(
        self,
        stage: str,
        model: str,
        kind: str = "",
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        seconds: float | None = None,
        added: int = 0,
        rejected: int = 0,
        reviewed: int = 0,
        flagged: int = 0,
        failed: bool = False,
        dry_run: bool | None = None,
    ) -> bool:
        try:
            folder = self.folder
            entry = {
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "project": folder.name,
                "run": self.run,
                "stage": str(stage)[:40],
                "model": str(model)[:120],
                "kind": str(kind)[:40],
                "prompt_tokens": _number(prompt_tokens),
                "completion_tokens": _number(completion_tokens),
                "seconds": round(float(seconds), 3) if seconds is not None else None,
                "added": int(added),
                "rejected": int(rejected),
                "reviewed": int(reviewed),
                "flagged": int(flagged),
                "failed": bool(failed),
                "dry_run": None if dry_run is None else bool(dry_run),
            }
            folder = claim_project_folder(self.root, self.home)
            with open(folder / LEDGER_NAME, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
        except Exception:  # deliberately broad: see the note at the top of the file
            return False
        return True


# A token count as a whole number, or nothing if the server gave none.
def _number(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


# Read the records of a ledger file, skipping lines that are not records.
def read_records(path: Path | str) -> list[dict]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    records = []
    for line in text.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            records.append(entry)
    return records
