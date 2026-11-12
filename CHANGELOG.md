# Changelog

All notable changes to this project are recorded here. Format based on
[Keep a Changelog](https://keepachangelog.com). Details on tests and decisions
are in [WORKLOG.md](WORKLOG.md).

## [Unreleased]

### Added

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

- `momus.argus.split_lines()` is now public: the splitter uses the same
  line splitting as the guard
- Chat explanations to the maintainer are now in English (`CLAUDE.md`,
  `plan-Momus.md`, `snapshot` skill)
