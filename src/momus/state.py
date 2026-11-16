# Where Momus keeps its own working files: outside the projects.
#
# The usage ledger and the backups live in the user's state folder
# (`$XDG_STATE_HOME/momus/<project>/`, or `~/.local/state/momus/<project>/`),
# one folder per project, named after the project's folder. A project's
# repository and its `.gitignore` are never touched. Paths are worked out at
# run time; nothing here is tied to one machine.

import hashlib
import os
import subprocess
from pathlib import Path

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


def _digest(root: Path) -> str:
    return hashlib.sha256(str(root).encode("utf-8", errors="surrogateescape")).hexdigest()


# The folder of one project under `home`, named after the project's folder.
#
# When another project with the same folder name already owns that folder, a
# short piece of a hash of this project's path is added to the name, and only
# then.
def project_folder(root: Path, home: Path | None = None) -> Path:
    home = home or state_home()
    name = root.name or "root"
    digest = _digest(root)
    plain = home / name
    try:
        owner = (plain / MARKER_NAME).read_text(encoding="utf-8").strip()
    except OSError:
        owner = ""
    if owner and owner != digest:
        return home / f"{name}-{digest[:4]}"
    return plain


# Create the folder of the project `root` and mark it as that project's, so
# the next project with the same folder name gets a folder of its own.
#
# Raises:
#     OSError: if the folder or its marker cannot be written.
def claim_project_folder(root: Path, home: Path | None = None) -> Path:
    folder = project_folder(root, home)
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / MARKER_NAME
    if not marker.exists():
        marker.write_text(_digest(root) + "\n", encoding="utf-8")
    return folder
