---
name: work-log
description: Keep CHANGELOG.md (what changed, for readers) and WORKLOG.md (tests run, choices made and why, for the maintainer) up to date. Use at the end of every plan step or any change to the repo, and when the user asks what was done, tested or decided.
---

# Changelog and worklog

Two files, two audiences, no duplicated text. If the project's `CLAUDE.md`
contradicts this skill, the project's file wins.

| File | Answers | Audience | Style |
|---|---|---|---|
| `CHANGELOG.md` | What changed in the project? | Users and contributors | Short, one line per change |
| `WORKLOG.md` | What was tested, what was decided, and why? | The maintainer, and future sessions | Dated, plain words, honest about gaps |

Link from one to the other instead of copying. A changelog line may point to
the worklog entry that explains it.

## When to run

At the end of **every plan step**, right before stopping to wait for the
maintainer's OK. Also after any change that touches the repo outside a plan
step (a new skill, a rule change, a fix).

## CHANGELOG.md

Format: [Keep a Changelog](https://keepachangelog.com), newest first.

- Entries go under `## [Unreleased]` until the maintainer asks for a release
- Groups: `Added`, `Changed`, `Fixed`, `Removed`
- One line per change, in English, written from the reader's point of view
  ("`momus guard` rejects code that does not parse"), not the author's
  ("fixed stuff")
- **Do not** rename `[Unreleased]` to a version, bump a version string, or
  create a tag. Releases and snapshots happen only on explicit instruction,
  through the `snapshot` skill

## WORKLOG.md

Newest entry first. One entry per step or change, using this template:

```
## YYYY-MM-DD — <short title> (plan §X, or "outside plan")

**Changed**
- <file>: <what and why, one line each>

**Tests**
- Command run: `<exact command>`
- Result: <passed/failed counts, copied from the real output>
- Not run / not verified: <say plainly what was skipped and why>

**Decisions**
- <choice made> — because <reason>. Alternatives considered: <short list>

**Open / next**
- <anything left, any question for the maintainer>
```

Rules:

- **Tests**: paste the real result. If no test was run, write "No tests run"
  and why (for example: no suite exists yet). Never write "passed" for
  something that was not executed
- **Decisions**: record the reason, not only the outcome. A decision made by
  the maintainer says "Decided by the maintainer"; a default picked by the
  assistant says "Assistant's choice, open to change"
- **Benchmarks**: raw numbers belong in `benchmarks/`, not here. Link to the
  file, and never state a performance number that was not measured
- Past entries are history: correct a mistake by adding a new dated note, do
  not rewrite the old entry

## Procedure

1. Read `git status` and `git diff --stat` to list what really changed. Do not
   write from memory
2. Add the changelog lines under `[Unreleased]`
3. Add the worklog entry on top
4. If a plan checkbox changed, make sure `plan-Momus.md` agrees with the
   worklog (only verified items checked)
5. Tell the maintainer in the end-of-step summary that both files were updated
6. Do not commit. Leave the files uncommitted and say they are ready
