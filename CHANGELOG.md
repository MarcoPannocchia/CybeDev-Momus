# Changelog

All notable changes to this project are recorded here. Format based on
[Keep a Changelog](https://keepachangelog.com). Details on tests and decisions
are in [WORKLOG.md](WORKLOG.md).

## [Unreleased]

### Added

- Quality rules (`momus.quality`) applied to everything Clio inserts, with no
  model call: tidier docstrings (consistent `Args`/`Returns`/`Raises`
  sections, no empty or "None" sections, no list of methods, lines wrapped to
  79 columns, a summary line), and inline comments dropped when they only
  describe or repeat the code. At most 3 comments per function
- Text copied from Momus's own instructions is rejected, for docstrings and
  comments alike
- `momus bench` also records the power source at the end of each model's run
- `momus review FILE... [--base REF]`: a strong model reads the comments and
  docstrings added to the files since `REF` (default `HEAD`) and prints
  `file:line: problem` for each false, redundant or inconsistent one. Changes
  that touch code are refused. The model sees each comment next to the code
  around it, in batches
- Review backends: `claude_code` (runs `claude -p` with tools off; no key) and
  `anthropic` (Messages API over plain HTTP; key from an environment
  variable), chosen in the new `[review]` table of `momus.toml`
- `momus bench`: runs Clio as a dry run with several models over the same
  files and writes, per model, a raw JSON file and a Markdown summary into
  `benchmarks/results/`, both starting with the measurement conditions (power
  source, load, free memory, Ollama version, quantization, cold or warm start,
  commit). The engine is `src/momus/bench.py`, reusable by a future app
- Outcomes now say what they are (`kind`: docstring or comment) and why a
  rejection happened (`cause`: backend, reply, anchor or guard)
- `LocalBackend.last_usage`: the token counts the server reported for the last
  reply
- Clio, inline comments: the model is shown a function with numbered
  statements (S1, S2, ...) and answers `S3: comment text`; Momus inserts the
  comment above that statement. Statements that already have a comment, `elif`
  branches and lines holding several statements are never offered. Each comment
  passes both Argus checks or is dropped
- `momus comment --mode {both,docstrings,comments}` (default `both`)
- Editable prompt file `src/momus/prompts/clio_comments.txt`
- Clio, docstring slice (`momus.clio`): adds a missing docstring to every
  function, method and class, with the text from the local model and the
  insertion done by Momus. Existing docstrings are never replaced. Every
  insertion must pass both Argus checks or it is dropped
- `momus comment FILE... [--write] [--model NAME] [--config PATH]`: shows a diff
  by default and writes only with `--write`, through an atomic replace
- Editable prompt file `src/momus/prompts/clio.txt`
- `momus.cleaning.strip_reasoning()`: the `<think>` removal step on its own
- `examples/retry.py` and five neutral sample files in `benchmarks/samples/`,
  the inputs of the model quality comparison (§9) and later the benchmark
- Output cleaner (`momus.cleaning.clean_output()`): removes `<think>` blocks
  and markdown fences, with the chatter around a fence, from a model reply
- File splitter (`momus.splitter.split_source()`): cuts a Python file into
  one piece per top-level function or class (decorators included) plus the
  lines between them; optionally one piece per method for large classes. The
  pieces rebuild the file exactly
- Argus second check (`check_inserted_lines()`): removing the lines Momus
  inserted must give the original text exactly, so reformatting, changed
  line endings and a changed final newline are rejected. Not wired into the
  pipeline yet
- Argus, the AST guard (`momus.argus`): `compare_code()` accepts a new text
  only if its code is identical to the original apart from comments and
  docstrings, and rejects anything it cannot analyse. Not wired into the CLI
  yet
- Backend layer: common `Backend` interface, `LocalBackend` (any OpenAI-format
  local server, such as Ollama, over plain HTTP) and `FakeBackend` for tests
- `momus.toml` example config and a loader (`momus.config`); the context size
  is left to the server
- `integration` test marker: tests needing a real Ollama are skipped by default
  (`pytest -m integration` runs them)
- Project skeleton: `pyproject.toml`, `src/momus` package and a `momus` CLI
  with placeholder subcommands `comment`, `guard`, `review`, `bench`
  (they exit with status 1 until implemented)
- `tests/test_smoke.py`: package import and CLI skeleton tests
- `requirements.txt` and `requirements-dev.txt` for one-command install
- `deps-sync` skill: keeps `requirements.txt` and `requirements-dev.txt`
  matched to the real dependencies, for one-command install
- `work-log` skill: keeps this changelog and `WORKLOG.md` up to date

### Changed

- Both Clio prompts rewritten: a fixed docstring style, comments only where a
  reason is hidden, and no examples (a small model copied them into the code)
- A method is shown to the model inside a `class X:` header instead of being
  described in a sentence
- `momus.argus.split_lines()` is now public: the splitter uses the same
  line splitting as the guard
- Chat explanations to the maintainer are now in English (`CLAUDE.md`,
  `plan-Momus.md`, `snapshot` skill)
