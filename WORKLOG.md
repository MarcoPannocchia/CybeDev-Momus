# Worklog

Tests run, choices made and why, newest first. Maintained by the `work-log`
skill. User-facing changes are summarized in [CHANGELOG.md](CHANGELOG.md).

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
