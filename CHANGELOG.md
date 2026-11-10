# Changelog

All notable changes to this project are recorded here. Format based on
[Keep a Changelog](https://keepachangelog.com). Details on tests and decisions
are in [WORKLOG.md](WORKLOG.md).

## [Unreleased]

### Added

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

- Chat explanations to the maintainer are now in English (`CLAUDE.md`,
  `plan-Momus.md`, `snapshot` skill)
