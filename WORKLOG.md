# Worklog

Tests run, choices made and why, newest first. Maintained by the `work-log`
skill. User-facing changes are summarized in [CHANGELOG.md](CHANGELOG.md).

## 2026-11-09 — Project skeleton (plan §5)

**Changed**
- `pyproject.toml`: setuptools backend, Python >=3.11, `src/` layout, `momus`
  console script, no runtime dependencies, `pytest` as dev extra
- `src/momus/__init__.py`, `src/momus/cli.py`: `argparse` CLI; subcommands
  `comment`, `guard`, `review`, `bench` are placeholders that print "not
  implemented yet" and exit 1
- `tests/test_smoke.py`: 7 tests (import, help, each placeholder command)
- `requirements.txt` (`-e .`) and `requirements-dev.txt` (`pytest==9.2.0`)
- `plan-Momus.md` §5 checkboxes; `.claude/skills/deps-sync/SKILL.md` now
  documents `-e .` in `requirements.txt`

**Tests**
- Command run: `.venv/bin/pytest` — result: 7 passed in 0.04s
- Command run: `.venv/bin/momus --help` — lists the four subcommands;
  `.venv/bin/momus guard` exits 1 with "momus guard: not implemented yet"
- Command run: `pip install --dry-run -r requirements-dev.txt` — resolves
- Not run: a clean install from `requirements.txt` in a fresh venv (it would
  download packages; not asked). No baseline run before the change, because no
  suite existed

**Decisions**
- `argparse` and `pytest` — approved by the maintainer
- setuptools as build backend — assistant's choice, open to change. It is the
  default pip uses and adds no runtime dependency
- Version `0.0.0` placeholder — assistant's choice; `CLAUDE.md` forbids setting
  a real version without a request
- Placeholders exit 1 instead of 0 — assistant's choice, so a stub can never
  look like a successful run
- `requirements.txt` holds `-e .` — assistant's choice, so one command installs
  the `momus` command. Alternative: an empty file, since there are no runtime
  dependencies

**Open / next**
- Skeleton changes are uncommitted; the plan's "first commit" waits for the
  maintainer's request
- `LICENSE` is CC0; §13 still lists the license as open
- Next plan step: §6, local backend (`qwen2.5-coder:1.5b`)

## 2026-11-09 — English chat rule synced everywhere (outside plan)

**Changed**
- `plan-Momus.md` (§0) and `.claude/skills/snapshot/SKILL.md`: chat language
  changed from Italian to English, matching `CLAUDE.md`

**Tests**
- No tests run: no suite exists yet
- Checked with `grep -rn -i "italian"` over the `.md` files (excluding
  `snapshots/`): the only remaining hits are the history notes in this file

**Decisions**
- Updated both files after the maintainer's OK; this resolves the open item in
  the entry below (past entries are not rewritten)

**Open / next**
- Next plan step: §5, project skeleton

## 2026-11-09 — Changelog, worklog and dependency skills (outside plan)

**Changed**
- `.claude/skills/deps-sync/SKILL.md`: new skill that writes direct
  dependencies to `requirements.txt` / `requirements-dev.txt`
- `.claude/skills/work-log/SKILL.md`: new skill for this file and the changelog
- `CHANGELOG.md`, `WORKLOG.md`: created
- `CLAUDE.md`: chat language changed from Italian to English; changelog and
  worklog added to the documentation rules

**Tests**
- No tests run: the project has no code and no test suite yet
- Not verified: neither skill has been run on a real project. `deps-sync` has
  nothing to scan until `src/` and `pyproject.toml` exist

**Decisions**
- English for chat — decided by the maintainer
- Skills for repeated procedures — decided by the maintainer; new skill
  candidates are proposed and created only after the maintainer agrees
- One `work-log` skill for both files instead of two — assistant's choice, open
  to change: they are always updated together
- `requirements.txt` lists direct dependencies only, pinned to the versions
  installed in the venv — assistant's choice, open to change. Alternative:
  full `pip freeze`, which is stricter but harder to maintain
- Changelog entries stay under `[Unreleased]` — releases need an explicit
  instruction, as `CLAUDE.md` already says

**Open / next**
- `.claude/skills/snapshot/SKILL.md` and `plan-Momus.md` still say Italian
  for chat. Waiting for the maintainer's OK to update them
- Next plan step: §5, project skeleton
