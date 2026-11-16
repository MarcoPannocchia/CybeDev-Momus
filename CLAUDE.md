# Momus — project instructions for Claude Code

Momus is a Python pipeline that comments and documents freshly written code
while spending few tokens. A local model (stage **Clio**) adds comments and
docstrings, an AST guard (stage **Argus**) rejects any output that changed the
code, and a stronger model (stage **Momus**, the critic) reviews a compact diff
of the comments only. Backends are interchangeable: nothing is tied to one
model or vendor.

Read this file before any change. If something here seems to contradict
`plan-Momus.md`, the plan wins on implementation details (order of steps,
module layout, open decisions); this file wins on process conventions
(how to work, what never to touch).

## Commands

> Several of these do not exist yet: the project is at the planning stage
> (see `plan-Momus.md`). Create them as the plan reaches the relevant step.

- Setup: `python3 -m venv .venv && source .venv/bin/activate`, then
  `pip install -e .` (once `pyproject.toml` exists)
- Tests: `pytest`
- CLI: `momus --help`, `momus comment`, `momus guard`, `momus review`,
  `momus bench`, `momus restore <file>`, `momus daemon {start,stop,status}` (the daemon is planned,
  §16.7)
- Local runtime check: `ollama list` (models are served by Ollama on
  `http://localhost:11434`; the `/v1` OpenAI-format endpoint is only a local
  transport protocol)

## How to work with the maintainer

- The maintainer is new to local models and LLM pipelines. Work **one plan step
  at a time**. At the end of each step: stop, explain what was written and why
  (in English, plain words), and wait for the OK before moving on
- Code, comments, docstrings, commit messages, README and this file are in
  **English**. Chat explanations to the maintainer are also in English
- The repository's own code (`src/`, `tests/`) is explained with `#` comments,
  **not docstrings**: a comment block above the definition, or inline. The one
  exception is the package docstring in `src/momus/__init__.py`. This is about
  the code of this repo, not about what Clio generates
- Say plainly what was not run or not verified. Never claim a test passed if it
  was not executed
- When asking the maintainer to run something, give **one command at a time**
  with a short explanation

## Hard rules (do not weaken without an explicit request)

These protect the one guarantee Momus makes: **it never changes code, only
comments and docstrings.**

- **No stage ever modifies code.** Clio may only add comments and docstrings
  where they are missing, and rewrite only those that Momus itself wrote
  (see `plan-Momus.md` §16.7, ownership). It never replaces a comment or
  docstring written by the maintainer or by another tool
- **Argus is the guard and it fails closed.** If the new code does not parse,
  is ambiguous, or differs from the original in anything except comments and
  docstrings, the output is discarded and the original is left untouched
- Never bypass, loosen or disable Argus to make a test, a model or a benchmark
  look better. If a test needs the guard skipped, the problem is in the test
- Ordinary string literals that are not docstrings must never be ignored by
  the guard
- **Dry-run is the default** for `momus comment`. Files are written only with
  `--write`
- **The one exception is the background daemon** (`momus daemon`, started with
  `/activate_momus`; planned, see `plan-Momus.md` §16.7). Activating it is the
  maintainer's explicit consent to write, equivalent to `--write`. The
  exception is narrow: manual `momus comment` runs stay dry-run by default,
  the daemon's output goes through Argus exactly like any other output, and
  before every write it saves a backup copy of the original file
- Any new feature that writes files, the daemon included, must go through the
  same guard path as Clio

## Test cycle

- At the start of a work session on a phase: run the existing suite and
  confirm it is green (baseline) before changing anything. If something already
  fails, stop and report it
- After each plan item: implement it, add the test it requires to the existing
  suite (not a standalone script), run the **whole** suite, confirm no
  regression, then move to the next item
- Argus gets the heaviest testing: every edge case listed in `plan-Momus.md`
  has its own test
- Tests never call a real model API. Use the fake backend. Calls to the local
  Ollama server belong in clearly marked integration tests or in the benchmark,
  not in the default suite
- Do not add tests beyond what the current item requires, on your own
  initiative

## Versioning (critical rule)

- The **live** working copy is `src/` plus the files in the repo root. **Always
  work on those.** Frozen copies live in `snapshots/vX.Y.Z/`. **Never modify
  them**: they are history, not documentation and not code to update
- A new snapshot is cut **only on explicit instruction** from the maintainer
  ("save as v0.2.0", "freeze this version"), using the `snapshot` skill
  (`.claude/skills/snapshot/SKILL.md`). Never on your own initiative
- A snapshot keeps the code together with the benchmark results and the
  environment they were measured in, so any number in the README can be traced
  to the code that produced it
- Git tags accompany snapshots, but are created only when the maintainer asks.
  `CHANGELOG.md` entries go under `[Unreleased]` as work happens; turning them
  into a versioned release is done only when the maintainer asks
- Do not bump version strings, create a tag or a release unless the maintainer
  explicitly asks
- Do not commit or push unless the maintainer explicitly asks. Leave changes
  uncommitted and say what is ready

## Where documentation goes

- `README.md` — user-facing: what it is, flow diagram, install, usage,
  benchmark summary, known limits, model-license note
- `plan-Momus.md` — working tool, not reference documentation. Update its
  checkboxes as steps complete; mark `[x]` only when verified
- `CHANGELOG.md` — what changed, one line per change, under `[Unreleased]`
  until a release is requested
- `WORKLOG.md` — tests run, choices made and why. Both files are updated at
  the end of every step with the `work-log` skill
- `requirements.txt` / `requirements-dev.txt` — kept in sync with the real
  dependencies by the `deps-sync` skill, for one-command install
- `benchmarks/` — raw benchmark results, one file per run, with the
  measurement conditions
- Do not create a second source of truth: if a concept is already documented in
  one place, link to it instead of copying
- When you change a function's signature, behavior or side effects, update the
  documentation that describes it in the same change

## Negative rules

- Do not add new dependencies without being asked
- **Do not download models** without asking: the maintainer's connection is
  slow. Use the models already installed (`qwen2.5-coder:1.5b`,
  `deepseek-coder-v2:16b`) and their original tags. `qwen2.5-coder:7b` and
  `qwen3-coder:30b` (~19 GB) are approved: the maintainer pulls them himself,
  and each can be used once it appears in `ollama list`. Do not pull them
  yourself
- Never commit model weights (`*.gguf`, `*.safetensors`), API keys, `.env`
  files or anything in `.gitignore`
- API keys live only in environment variables (e.g. `ANTHROPIC_API_KEY`),
  never in code, `momus.toml` or fixtures
- No private or sensitive code in tests, fixtures or examples: only neutral
  functions written for the purpose
- Do not hard-code machine-specific paths (home folders, venv locations)
- Do not claim a performance number you did not measure. Label estimates as
  estimates, in code comments and in the README too

## Measurement conditions (for any benchmark number)

Record: mains power vs battery, power profile, model and quantization, Ollama
version, cold vs warm model load, and that other heavy applications were
closed. Prompt-eval numbers taken right after a cold load, or on a repeated
identical prompt, are not reliable.

## Definition of done

A change is complete when: the full test suite is green, Argus's behavior is
unchanged or intentionally extended with tests, `plan-Momus.md` reflects the
real state (only verified items checked), and any documentation describing the
changed behavior is updated in the same change.