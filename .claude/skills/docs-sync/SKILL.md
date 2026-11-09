---
name: docs-sync
description: Keep a project's user documentation and developer reference matched to its live source code after changes, and audit documentation drift. Use when the user asks to update, check or fill the documentation, or after a function signature, behavior or side effect changes.
---

# Documentation sync

Keeps two documentation trees aligned with the live code:

- **User docs**: answers "what is it and how do I run it". Audience: people who use the project.
- **Developer reference**: answers "what does each function do, and where is the upstream documentation of the libraries it calls". Audience: people who change the code.

If the project's own instructions file (for example `CLAUDE.md`, `AGENTS.md` or a README section on contributing) contradicts this skill, the project's file wins.

## Project configuration

Fill this in once per project. The rest of the skill refers to these names.

- `SOURCE_DIRS`: live code folders, for example `src/`
- `USER_DOCS`: user documentation folder, for example `docs/user/`
- `DEV_DOCS`: developer reference folder, for example `docs/dev/`
- `VERSIONED_DIRS`: frozen snapshot folders that must never be edited, for example `releases/` or `versions/`. Leave empty if none
- `PROCESS_FILES`: planning and changelog files that are updated only on request, for example `CHANGELOG.md`, `PLAN.md`
- `RETIRED_NAMES`: names that must not reappear in code or docs, for example an old project name. Leave empty if none
- `VERSION_SOURCE`: where the version string lives, for example `app/version.py`. Leave empty if none

If a value is not filled in, ask the user for it before running the drift checks.

## Rules that do not change

- Work only on the live tree. Never edit anything under `VERSIONED_DIRS`. Those folders are history.
- Update the developer reference whenever a signature, behavior or side effect changes.
- Update the user docs only when the change is visible to a user: a new command, a new requirement, different output.
- Link, do not copy. If a concept lives in one tree, the other tree links to it. Never create a third source of truth.
- Copy signatures from the source verbatim. Never paraphrase them.
- Do not bump version strings. Do not edit `PROCESS_FILES` unless the user asks. Report what should change there instead.
- Keep internal-only modules out of the user docs on purpose. Say so in the index of the user docs if it is not already said.
- Do not put text documentation in asset folders. They hold images only.
- Do not use names listed in `RETIRED_NAMES` in new code, comments or docs. Historical notes in the changelog are allowed.
- Do not commit. Leave changes in the working tree and say what is ready.

## Steps

1. **Find what changed.** If the project is a git repository, use `git diff --name-only` against the last commit. Otherwise compare the live source with the most recent snapshot in `VERSIONED_DIRS`, with read-only diffs such as `diff -rq <snapshot>/<source> <source> -x __pycache__`.
2. **List the changed symbols.** For each changed function, method or class, note what changed: signature, behavior or side effect. A refactor with no behavior change needs no documentation edit.
3. **Find the page.** Search both doc trees for the symbol name, for example `grep -rn "<name>" <DEV_DOCS>`. If a name appears in no page, that is a gap. Report it, and add a page only if the user asked for coverage.
4. **Edit the developer reference first.** Copy the new signature from the source. Describe behavior and side effects in the words the code uses. Keep the page structure that already exists.
5. **Decide on the user docs.** Ask: can a user see this change in a command, a requirement or an output? If yes, update the matching page in `USER_DOCS` in plain language, with no internal names. If not, leave it.
6. **Run the drift checks below** and fix only what this change caused. Report the rest.
7. **Report back**: pages changed, pages intentionally left alone and why, check results, and anything that needs a decision.

If a page for a changed module does not exist yet, create the page structure only after the user confirms where it should go.

## Drift checks

Run from the project root. These only read files.

```bash
# 1. Retired names (exclude the changelog, which may mention them as history)
grep -rIn -e "<RETIRED_NAME_1>" -e "<RETIRED_NAME_2>" SOURCE_DIRS USER_DOCS DEV_DOCS --exclude=CHANGELOG.md || echo "no retired names"

# 2. Version string against the top changelog heading (report only, never bump)
grep -rn "<version pattern>" <VERSION_SOURCE>
grep -n "^## " CHANGELOG.md | head -1

# 3. Page parity between the two doc trees
diff <(cd USER_DOCS && find . -name '*.md' | sort) <(cd DEV_DOCS && find . -name '*.md' | sort)

# 4. Every developer page is linked from the developer index
grep -c "<module folder name>/" <DEV_DOCS>/index.md
```

Expected differences in check 3 are intentional. Write them in the project's own index so that a future run does not flag them as errors. Do not "fix" them.

## Pitfalls

- A documentation page changed without a matching source change is a red flag. Check the source first.
- Write what the code does, not what a plan says it should do. Do not call something verified unless you checked the source line.
- The user may be editing the same files. Re-read a page before writing to it.
- Do not run any command that changes files in `VERSIONED_DIRS`, including formatters and test runs that write caches.