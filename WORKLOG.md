# Worklog

Tests run, choices made and why, newest first. Maintained by the `work-log`
skill. User-facing changes are summarized in [CHANGELOG.md](CHANGELOG.md).

## 2026-11-12 — Sample files for the quality comparison (plan §9)

**Changed**
- `examples/retry.py`: the 9-line function of the plan's "done when"
- `benchmarks/samples/`: `stats.py`, `inventory.py`, `async_tools.py`,
  `report_lines.py`, `text_tools.py` (41-47 lines each, 2-6 functions or
  classes each, written for the purpose, no private code)
- `plan-Momus.md` §9: note on where the files are; the comparison stays open

**Tests**
- Each file parses, splits with `split_source()` and passes `compare_code()`
  against itself; the largest function or class is 12 lines, except
  `Inventory` (40 lines, one class)
- A one-off script (not added to the suite, since the samples are data, not
  project code) ran their behaviour: `retry` with a flaky function, `median`,
  `normalize`, `moving_average`, `Inventory` add/remove, `gather_limited`,
  `fibonacci(30)`, `Report.summary`, `top_words`, `truncate`, `wrap`. All
  passed
- Whole suite: `.venv/bin/pytest` — 134 passed, 1 deselected
- Not run: any model on these files

**Decisions**
- Location `benchmarks/samples/` — assistant's choice, open to change: the plan
  does not say, and §11 reuses the same files
- Coverage: plain functions (`stats`, `text_tools`), a class with a property
  and a static method (`inventory`), decorators and async code
  (`async_tools`), and hand-written docstrings and comments that Momus must
  not replace (`report_lines`; ownership rule, §16.7)
- Only the samples have no docstrings except `report_lines`, so every model
  has work to do on four of five files

**Open / next**
- Design of the Clio prompt and the docstring-only reply format, for the
  maintainer's OK before any model runs
- Uncommitted: all of the above

## 2026-11-12 — Output cleaning and file splitting (plan §8)

**Changed**
- `src/momus/cleaning.py`: `clean_output()`
- `src/momus/splitter.py`: `split_source()`, `join_pieces()`, `Piece`,
  `SplitError`
- `src/momus/argus.py`: `_split_lines` renamed to the public `split_lines`
  (no behaviour change), so the splitter shares it
- `tests/test_cleaning.py` (15 tests), `tests/test_splitter.py` (29 tests)
- `plan-Momus.md`: §8 and §15 item 4 checked; reference state updated

**Tests**
- Baseline before changes: `.venv/bin/pytest` — 90 passed, 1 deselected
- After: `.venv/bin/pytest` — 134 passed, 1 deselected (integration)
- Not run: the cleaner on real model replies (examples were written by hand);
  the splitter on real project files; Python versions other than 3.12.3

**Decisions**
- The cleaner keeps the inside of the **first** fenced block and drops the
  rest — assistant's choice. Without a fence it does not guess where chatter
  ends: "Here is the code:" glued to an answer stays, and Argus rejects it.
  Guessing could delete a real line
- An unclosed `<think>` block leaves an empty answer; an orphan `</think>`
  drops everything before it — assistant's choice
- The cleaner is format-agnostic on purpose: the reply format of §9
  (docstring text, "S3: comment" pairs) is not fixed yet, so stripping the
  quotes around a docstring is left to §9
- Pieces cover **every** line (kind `other` for imports, constants, comments,
  blank lines), so reassembly is a plain join. A comment block right above a
  function lands in the `other` piece before it — known limit, to revisit in
  §9 if the model needs that context
- Per-method splitting is opt-in through `max_class_lines`, default off —
  assistant's choice: the plan says large classes "can be" split, and the
  right threshold needs real files. A split class yields `method` pieces and
  `class-part` pieces (header, attributes, lines between methods); these are
  indented fragments and do not parse on their own
- Nested functions and classes are never split off
- `split_source()` re-joins its own pieces and raises `SplitError` if they
  do not give the source back — fail closed, same spirit as Argus

**Open / next**
- §9, Clio. Its first task is the quality comparison on 5 neutral files
- Uncommitted: all of the above

## 2026-11-12 — Argus, part 2: byte-level check on inserted lines (plan §7)

**Changed**
- `src/momus/argus.py`: `check_inserted_lines(original, new, inserted_lines)`
  and the private `_split_lines()`
- `tests/test_argus.py`: 31 more tests (67 in the file)
- `plan-Momus.md` §7: the second check and the build order checked

**Tests**
- Baseline before changes: `.venv/bin/pytest` — 59 passed, 1 deselected
- After: `.venv/bin/pytest` — 90 passed, 1 deselected (integration)
- Not run: Python versions other than 3.12.3; the check on real inserted
  lines, because the insertion step (§9) does not exist yet

**Decisions**
- Text is compared as Python `str`, not as `bytes` — assistant's choice. Equal
  characters mean equal bytes in any single encoding. Reading and writing the
  file without changing its encoding, its BOM or its newlines is the job of
  the write path in §9 and is **not** covered here
- Lines are split only on `\n`, `\r\n` and `\r`, not with `str.splitlines`,
  which also splits on form feeds and Unicode separators and would give line
  numbers different from the ones `ast` reports
- Mixed line endings are looked for in both texts together. So a file that
  already mixes endings is rejected even with nothing inserted — assistant's
  choice, the strict reading of "fail closed": Momus will refuse such files
  until someone decides otherwise
- An inserted last line without a final newline is accepted when the
  original bytes are intact (`"x = 1\n"` → `"x = 1\n# note"`). Adding a
  newline to the original's last line, or removing its final newline, is
  rejected
- Line numbers must be real integers; `True`, `2.0` and `"2"` are rejected
- The function does not check that the inserted lines are comments. That is
  the tree comparison's job: both checks must pass

**Open / next**
- §7 "Done when" also asks that the maintainer can explain the logic in plain
  words
- `momus guard` is still a placeholder; wiring both checks in is §9
- Uncommitted: all of the above

## 2026-11-12 — Argus, part 1: core comparison (plan §7)

**Changed**
- `src/momus/argus.py`: `compare_code()`, `code_fingerprint()`,
  `normalized_tree()`, `Verdict`, `ArgusError`
- `tests/test_argus.py`: 36 tests, one or more per edge case of §7
- `plan-Momus.md` §7: items up to the `(1,)` test checked; the second check,
  the build order and the ownership note stay open

**Tests**
- Baseline before changes: `.venv/bin/pytest` — 23 passed, 1 deselected
- After: `.venv/bin/pytest` — 59 passed, 1 deselected (integration)
- Checked by hand which path the "too deep" cases take on CPython 3.12.3:
  depth 100 000 fails in the parser (`MemoryError`), depth 5 000 parses but
  fails in `ast.dump` (`RecursionError`); both are rejected
- Not run: any Python version other than 3.12.3 (the project allows 3.11+);
  Argus on real model output; `momus guard` is still a placeholder

**Decisions**
- A docstring-only body equals a `pass`-only body, for functions, async
  functions and classes — as the plan says. Consequence: replacing `pass` with
  a docstring passes this comparison; the byte-level check of part 2 is what
  catches it
- A module is not given a `pass`: an empty module is legal, so a module with
  only a docstring equals an empty one but not one containing `pass` —
  assistant's choice, the stricter reading
- An unparseable **original** is rejected too — assistant's choice: nothing
  can be proven about the new text
- The parser's exceptions are caught broadly (`except Exception`) and turned
  into `ArgusError` — assistant's choice: for a guard every failure means "not
  provably safe"
- `compare_code()` returns a `Verdict` with a reason instead of a bare bool —
  assistant's choice, so rejected pieces can be listed with their cause (§9).
  `Verdict` has no truth value on purpose: callers must read `.accepted`
- Docstring rule copied from Python itself: first statement, plain string
  constant. F-strings, bytes and string expressions stay code

**Open / next**
- Part 2 of §7: the byte-for-byte check on inserted lines, after the
  maintainer's OK
- Uncommitted: all of the above

## 2026-11-10 — Local backend (plan §6)

**Changed**
- `src/momus/backends/__init__.py`: `Backend` protocol and `BackendError`
- `src/momus/backends/local.py`: `LocalBackend`, one POST to
  `/v1/chat/completions` with `urllib`; HTTP, network and malformed-reply
  failures all become `BackendError`
- `src/momus/backends/fake.py`: `FakeBackend` (canned replies, records prompts)
- `src/momus/config.py` and `momus.toml`: `[local]` settings; unknown keys and
  invalid TOML are rejected; a missing file gives defaults
- `tests/test_backends.py`: 16 tests (the local client runs against a stub HTTP
  server on localhost, no model involved), plus 1 integration test
- `pyproject.toml`: `integration` marker, skipped by default
- `plan-Momus.md` §6 and §15 item 2 checked

**Tests**
- Baseline before changes: 7 passed (`.venv/bin/pytest`)
- After: `.venv/bin/pytest` — 23 passed, 1 deselected (integration)
- `.venv/bin/pytest -m integration` — 1 passed against the real Ollama
- Manual check, three real models through `LocalBackend` with a one-sentence
  prompt: `qwen2.5-coder:1.5b` 1.6s (already loaded), `qwen2.5-coder:7b` 11.8s,
  `deepseek-coder-v2:16b` 11.1s, each with a sensible reply. These timings
  include model load, were taken without recording power or load conditions,
  and are **not benchmark numbers**
- Context test, one run on Ollama 0.23.3: sending `options.num_ctx=2048` to
  `/v1/chat/completions` was ignored (`ollama ps` still showed 4096)
- Not run: `qwen3-coder:30b`; the CLI is not wired to the backend yet

**Decisions**
- Plain HTTP (`urllib`) and the `/v1` endpoint — decided by the maintainer:
  no dependency, portable across Ollama / llama.cpp / LM Studio, and Ollama
  stays customizable by the user
- No `num_ctx` key in `momus.toml` — follows from the `/v1` choice; an unknown
  key is rejected so nobody believes it has an effect
- `max_tokens` and `timeout` added to the config — assistant's choice, open to
  change: output length dominates time on this CPU, and large models load slowly
- Stub-server tests instead of mocking `urllib` — assistant's choice: they
  exercise the real request path without any model

**Open / next**
- Uncommitted: all of the above, waiting for the maintainer
- Next plan step: §7, Argus (AST guard), with tests for every edge case

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
