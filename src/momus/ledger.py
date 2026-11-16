# The usage ledger: one line per model call, counts only.
#
# Every call Clio or the reviewer makes is recorded as one JSON object on its
# own line: when, which project, which stage and model, the tokens in and out,
# the seconds it took and what came of it (docstrings added, comments flagged).
# A record never holds code, comment text or a file name, so the file can be
# shown or shared without leaking anything.
#
# The file lives outside the projects, in the user's state folder
# (`$XDG_STATE_HOME/momus/<project>/usage.jsonl`, or `~/.local/state/...`), so
# a project's repository and its `.gitignore` are never touched.
#
# Recording must never be able to fail a run: every write swallows its errors
# and reports them with a return value nobody is obliged to read.

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

LEDGER_NAME = "usage.jsonl"
# Holds a hash of the project's path, to tell two projects with the same
# folder name apart without writing the path itself anywhere.
MARKER_NAME = "project-id"


# The folder all of Momus's working files live under, resolved at run time.
def state_home() -> Path:
    base = os.environ.get("XDG_STATE_HOME", "")
    # The XDG rules say a relative path here is to be ignored.
    root = Path(base) if os.path.isabs(base) else Path.home() / ".local" / "state"
    return root / "momus"


# The project a command is run in: the top of the git repository that holds
# `start`, or `start` itself when there is none.
def project_root(start: Path | str = ".") -> Path:
    try:
        done = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        top = done.stdout.decode("utf-8", errors="replace").strip() if done.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        top = ""
    return Path(top) if top else Path(start).resolve()


# The folder of one project under `home`, named after the project's folder.
#
# When another project with the same folder name already owns that folder, a
# short piece of a hash of this project's path is added to the name, and only
# then.
def project_folder(root: Path, home: Path | None = None) -> Path:
    home = home or state_home()
    name = root.name or "root"
    digest = hashlib.sha256(str(root).encode("utf-8", errors="surrogateescape")).hexdigest()
    plain = home / name
    try:
        owner = (plain / MARKER_NAME).read_text(encoding="utf-8").strip()
    except OSError:
        owner = ""
    if owner and owner != digest:
        return home / f"{name}-{digest[:4]}"
    return plain


# Writes the records of one run of a command for one project.
class Ledger:
    def __init__(self, root: Path | str | None = None, home: Path | None = None) -> None:
        try:
            self.root = project_root(root or ".")
            self.folder = project_folder(self.root, home)
        except Exception:  # an unreadable folder must not stop the command
            self.root, self.folder = Path("."), None
        self.project = self.folder.name if self.folder else "unknown"
        now = datetime.now(timezone.utc)
        # One id per command run, so the calls of a run can be added up.
        self.run = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}"

    @property
    def path(self) -> Path | None:
        return self.folder / LEDGER_NAME if self.folder else None

    # Append one record. Returns whether it was written; never raises.
    #
    # Only numbers, true/false and the three names below are accepted, which
    # is what keeps code and comment text out of the file.
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
            entry = {
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "project": self.project,
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
            self.folder.mkdir(parents=True, exist_ok=True)
            marker = self.folder / MARKER_NAME
            if not marker.exists():
                digest = hashlib.sha256(str(self.root).encode("utf-8", errors="surrogateescape"))
                marker.write_text(digest.hexdigest() + "\n", encoding="utf-8")
            with open(self.path, "a", encoding="utf-8") as handle:
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
