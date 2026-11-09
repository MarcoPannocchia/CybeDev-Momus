---
name: deps-sync
description: Keep requirements.txt (and requirements-dev.txt) matched to the dependencies the project really uses, so anyone can install everything with one command. Use when the user asks to write, update or check the requirements file, after a dependency is added or removed, or before a snapshot or release.
---

# Dependency sync

Writes every third-party dependency into `requirements.txt` so a stranger can
run **one command** and get a working environment:

```
pip install -r requirements.txt
```

Development tools (test runner and similar) go in `requirements-dev.txt`, which
starts with `-r requirements.txt`, so contributors also need only one command:

```
pip install -r requirements-dev.txt
```

If the project's own instructions file (`CLAUDE.md`) contradicts this skill,
the project's file wins.

## Project rules this skill must respect

- **Never add a dependency on its own initiative.** This skill records what the
  project already uses or what the maintainer approved. If the scan finds an
  import that no one approved, report it and ask
- **Never run `pip install` without asking.** Reading the environment
  (`pip list`, `pip freeze`, `pip show`) is fine
- **Never download models.** Model weights are not Python dependencies and
  never belong in a requirements file. Ollama models are documented in the
  README, not here
- No machine-specific paths, no `-e /home/...`, no local wheels, no index URLs
  with credentials, no API keys

## Procedure

1. **Collect what is declared.** Read `pyproject.toml` (`[project]
   dependencies` and optional dev dependencies) if it exists
2. **Collect what is actually imported.** Scan the live source (`src/`, never
   `snapshots/`) for `import x` / `from x import y` with `ast`, not with grep,
   so strings and comments are not counted. Drop the standard library
   (`sys.stdlib_module_names`) and the project's own package (`momus`)
3. **Map import names to PyPI names.** They often differ (for example `yaml` is
   `PyYAML`, `PIL` is `Pillow`). Check with `pip show` or
   `importlib.metadata.packages_distributions()`. If the mapping is uncertain,
   ask
4. **Compare** the three sets: declared, imported, currently installed.
   Report, in plain words:
   - imported but not declared (missing from the project)
   - declared but never imported (possibly unused, possibly only used at run
     time, so do not remove silently)
   - installed version differs from the version in the file
5. **Pin versions.** Use the version installed in the active virtual
   environment, written as `name==X.Y.Z`. Only direct dependencies are listed,
   not their sub-dependencies, so pip can resolve those itself. If the virtual
   environment is not active or the package is not installed, say so and write
   the name with the lower bound from `pyproject.toml` instead of inventing a
   version
6. **Write the files**, sorted alphabetically, one requirement per line, with a
   short header comment saying which command installs them and that the file is
   managed by this skill
7. **Verify.** Create a throwaway virtual environment in the scratchpad (not in
   the repo), run `pip install -r requirements.txt` there, and import the
   package. Only do this after asking, because it downloads packages. If it
   was not run, say plainly that the file is unverified
8. **Keep one source of truth.** If `pyproject.toml` exists, its dependency
   list and `requirements.txt` must not disagree. Update `pyproject.toml` only
   when the maintainer approves; otherwise report the difference

## Output format

```
# Managed by the deps-sync skill. Install with: pip install -r requirements.txt
anthropic==X.Y.Z
openai==X.Y.Z
```

`requirements-dev.txt`:

```
# Managed by the deps-sync skill. Install with: pip install -r requirements-dev.txt
-r requirements.txt
pytest==X.Y.Z
```

## Before finishing

- Tell the maintainer which files changed and why each line is there
- State what was not verified (for example: versions taken from the active
  environment, clean install not tested)
- If the README has an install section, check that it shows the one-command
  install and matches the file names; update it in the same change
- Do not commit. Leave the files uncommitted and say they are ready
