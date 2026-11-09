# Plan — Momus

<!-- markdownlint-disable MD003 MD013 MD022 MD028 MD036 MD040 MD060 -->

Task list to track project development. Update the checkboxes as steps get
completed. This file is written to be read by an AI coding agent (e.g. a Claude
Code session) as well as by a human: every step has an explicit "Done when"
criterion, and anything not yet verified is marked as such.

---

## 0. Conventions for this file

- `[x]` = done **and verified** (tests green, command run, output checked)
- `[ ]` = to do, or done-but-unverified (say which in the line)
- Each section is a project area or a decision already made in chat
- Dates are ISO (`YYYY-MM-DD`). Decisions carry the date they were made
- Reference state for the latest update of this plan: **pre-v0.1.0, no code
  written yet**. Last updated **2026-11-09**
- Language rules: this plan, all code, comments, docstrings, commit messages
  and the README are in **English**. Explanations to the maintainer in chat are
  also in English

**Working rules for the agent (read before touching anything)**

- The maintainer is new to local models and LLM pipelines. Work **one step at a
  time**: at the end of each step, stop, explain what was written and why, and
  wait for the OK before the next step
- State plainly what was not run or not verified. Never mark `[x]` on
  something that was only written, not executed
- No sensitive or private code in tests, fixtures or examples: only neutral
  functions written for the purpose
- Never commit model weights, API keys or `.env` files
- Ask before installing a new dependency, and **before downloading any model**
  (the maintainer's internet connection is slow). Exception: `qwen2.5-coder:7b`
  and `qwen3-coder:30b` are already approved (2026-11-09) and are to be pulled
  by the maintainer

---

## 1. What Momus is

A Python pipeline that comments and documents freshly written code while
spending few tokens. A **local model** does the repetitive work; a **stronger
model** does only the final review. The name comes from Momus, the Greek god of
mockery and fault-finding: the project does not trust generated comments and
checks them.

Goal: a clean public GitHub repo for a portfolio — README, before/after
examples and an honest benchmark that also shows the failures.

**Three stages (named after Greek figures)**

1. **Clio** (local model): adds only comments and docstrings, one function or
   class at a time
2. **Argus** (AST guard): compares code before and after, ignoring comments and
   docstrings. If the code changed, the output is discarded
3. **Momus** (strong model): receives a compact diff of the comments only and
   flags false, redundant or inconsistent ones

Planned CLI: `momus comment`, `momus guard`, `momus review`, `momus bench`.

---

## 2. Decisions already made

- [x] **Name: Momus** — decided 2026-11-08. Internal stages: Clio / Argus /
      Momus (critic). Still to check: no confusing name clash on GitHub (see §13)
- [x] **Backends are interchangeable** — decided 2026-11-08. No stage is tied
      to one model or vendor. The local stage talks to any local runtime
      (Ollama, llama.cpp, LM Studio) through its OpenAI-format endpoint, which is
      used **only as a local transport protocol**; the review stage uses Claude
      via the Anthropic API or via Claude Code in non-interactive mode
      (`claude -p`)
- [x] **Python only for v0.1** — decided 2026-11-08
- [x] **Argus is built before Clio** — decided 2026-11-09: it is the critical
      and most original part, and it must exist before any file gets written
- [x] **Dry-run by default** — decided 2026-11-09: Clio shows a diff and only
      writes with `--write`
- [x] **Use a non-reasoning code model for Clio** — decided 2026-11-09 (working
      hypothesis, to be confirmed by the benchmark): reasoning models spend time
      in a `<think>` block, which is wasted on CPU for a task whose input
      already contains the code
- [ ] **Output mode for Clio — open decision** (see §9): *full-rewrite* (model
      returns the whole code, Argus verifies) vs *docstring-only* (model returns
      only the docstring text, Momus inserts it programmatically). Decide after
      the first quality comparison

> **Note**: the license choice for the repo is not made yet (§13). Model
> weights are never shipped in the repo; the README only says how to download
> them and links to their licenses.

---

## 3. Environment and measured baseline

**Machine**: ThinkPad L14 Gen 1, Ryzen 5 4650U Pro, 32 GB RAM, no dedicated
GPU, Linux Mint, 1 TB SSD. Inference is CPU-only, so the pipeline is designed
as a **batch job**, not an interactive tool.

**Runtime**: Ollama, server on `http://localhost:11434`, OpenAI-format endpoint
on `/v1`.

**Models available locally and to be used in tests** (use the original tags,
not customized variants, so system prompts do not distort the comparison):

- `qwen2.5-coder:1.5b` (~1 GB) — installed
- `deepseek-coder-v2:16b` (~8.9 GB) — installed
- `qwen2.5-coder:7b` (~4.5 GB, size is an estimate) — **approved 2026-11-09,
  not installed yet**. Pull with `ollama pull qwen2.5-coder:7b` (the pull
  normally resumes if interrupted). Check the exact tag on
  `ollama.com/library/qwen2.5-coder` first. Expected role: the middle option
  between the 1.5B (fast, possibly too weak) and the 16B
- `qwen3-coder:30b` (~19 GB download, MoE with ~3.3B active parameters) —
  **approved 2026-11-09, not installed yet**. Pull it overnight with
  `ollama pull qwen3-coder:30b`. Before pulling: check free disk (`df -h`, at
  least ~30 GB), keep the laptop on mains power with sleep disabled so the
  download is not interrupted. Memory: the weights alone take ~19 GB of the
  32 GB, so close other heavy applications and keep the context at ~8k
  (`num_ctx 8192`). Speed on this CPU is **not measured**: any expectation is
  an estimate. Expected role: the quality ceiling of the comparison, not
  automatically the default

> Do **not** download any other model without asking: slow connection.
> Candidate considered and deferred: `granite4:3b` (~2.1 GB). Check exact tags
> on `ollama.com/library` before pulling.

**First measurements** (function `retry`, 8 lines, mains power connected,
2026-11-09):

| | deepseek-coder-v2:16b | qwen2.5-coder:1.5b |
|---|---|---|
| Generation | 16.3 tok/s (cold), 17.3 tok/s (warm) | 27.4 tok/s (cold) |
| Load time | 11.5 s (cold), 0.1 s (warm) | 2.0 s (cold) |
| Prompt eval | **unreliable** | 89 tok/s (cold) |
| Total | 18.4 s (cold), 6.7 s (warm) | 7.5 s |

- [x] Ollama installed and both models respond — verified 2026-11-09
- [x] First throughput numbers collected — 2026-11-09 (1.5B and 16B only)
- [ ] `qwen2.5-coder:7b` pulled, responds, and throughput measured with the
      same `retry` test and the same conditions as the table above
- [ ] `qwen3-coder:30b` pulled (complete, checked with `ollama list`),
      responds, and throughput + memory use measured with the same `retry` test
      and conditions. Record cold-load time separately: loading ~19 GB may take
      far longer than the 16B's ~11 s
- [ ] **Quality comparison not done yet**: was the code left identical apart
      from the docstring? Was extra text or a markdown fence added? Is the
      docstring correct? This is the first task of §9
- [ ] Prompt-eval rate for the 16B was measured right after a cold load, and
      the warm value (1378 tok/s) is suspiciously high (possible prompt cache).
      Re-measure on real, different files
- [ ] Observed: the 1.5B is only ~60% faster than the 16B MoE (few active
      parameters per token). Speed alone will not decide the default model —
      the acceptance rate from Argus will

> **Measurement conditions to record in every benchmark**: mains power vs
> battery, power profile, model + quantization, Ollama version, whether the
> model was cold or warm, close other heavy applications.

---

## 4. Repo structure (target)

```
momus/
├── README.md
├── pyproject.toml
├── .gitignore            # created / to verify (see §5)
├── momus.toml            # example config, no secrets
├── src/momus/
│   ├── __init__.py
│   ├── cli.py
│   ├── clio.py           # commenting with the local model
│   ├── argus.py          # AST guard
│   ├── critic.py         # review with the strong model
│   ├── splitter.py       # split a file into functions/classes
│   ├── cleaning.py       # clean model output
│   └── backends/
│       ├── local.py          # Ollama / llama.cpp / LM Studio
│       ├── anthropic.py      # Claude via API (key from env var)
│       └── claude_code.py    # Claude Code non-interactive (claude -p)
├── tests/
│   ├── test_argus.py
│   ├── test_cleaning.py
│   └── fixtures/
├── examples/
│   ├── retry.py
│   └── retry.commented.py
├── benchmarks/
└── assets/               # logo
```

---

## 5. Phase A — Project skeleton

- [ ] `git init` and virtual environment in the project folder — commands were
      given 2026-11-09, **not confirmed as run**
- [ ] `.gitignore` covering `.venv/`, `__pycache__/`, `*.gguf`,
      `*.safetensors`, `.env`, `.env.*`, `*.key`, `config.local.*`, editor
      files — content was given 2026-11-09, **not confirmed as created**;
      verify with `git status` that `.venv/` is not listed
- [ ] `pyproject.toml` (Python 3.11+), `src/momus` package, CLI with `--help`
      and empty subcommands
- [ ] Smoke test that imports the package
- **Done when:** `momus --help` works and `pytest` passes

---

## 6. Phase B — Local backend

- [ ] Common backend interface: one function that takes a prompt and returns
      text; all backends implement it
- [ ] `backends/local.py`: client for the local server (the `openai` library
      pointed at `localhost`, or plain HTTP — explain the choice)
- [ ] Parameters read from `momus.toml`: base URL, model name, temperature
      (default 0), max context (start with `num_ctx` ~8192; Ollama's default is
      small and a huge context eats RAM)
- **Done when:** a script calls `qwen2.5-coder:1.5b` and prints the answer

---

## 7. Phase C — Argus (AST guard), built before Clio

- [ ] `argus.py`: a function taking original code and new code and returning
      whether the **code** is identical
- [ ] Method: parse both with Python's `ast`, remove docstrings (module, class,
      function, async function), compare `ast.dump` without attributes. `#`
      comments are not in the AST, so they are already ignored
- [ ] Edge cases to handle explicitly:
  - [ ] A function whose body is only a docstring becomes empty after removal —
        normalize to `pass` on both sides
  - [ ] Ordinary string literals that are **not** docstrings must **not** be
        ignored
  - [ ] Unparseable new code → discard (fail closed)
  - [ ] Never ignore f-strings or other string-like expressions
- [ ] Tests in `tests/test_argus.py`:
  - [ ] same code + docstring added → accepted
  - [ ] renamed variable → discarded
  - [ ] line of code added or removed → discarded
  - [ ] string literal changed → discarded
  - [ ] invalid output → discarded
- **Done when:** all tests pass and the maintainer can explain the logic in
  plain words

---

## 8. Phase D — Output cleaning and file splitting

- [ ] `cleaning.py`: strip markdown fences (```), leading/trailing chatter
      ("Here is the code…"), `<think>` blocks if a reasoning model is used. Tests
- [ ] `splitter.py`: split a file into top-level functions and classes using
      `ast` line numbers (`lineno`/`end_lineno`; include decorators); large
      classes can be split per method. Each model request stays small
- [ ] Verify that reassembling the untouched pieces reproduces the original file
      byte for byte
- **Done when:** tests on a file with several functions, including decorators

---

## 9. Phase E — Clio (`momus comment`)

- [ ] Reads the given files or the modified ones (`git diff --name-only`),
      splits them, sends each piece to the local model, cleans the output,
      passes it to Argus
- [ ] Prompt in English, kept in a **separate, easily editable file**. Intent:
      "Add concise docstrings and comments explaining WHY, not what. Do not change
      any code. Output only the code."
- [ ] Safe behavior: **dry-run by default** (show diff, write nothing);
      `--write` applies. Pieces rejected by Argus stay untouched and are listed
- [ ] Before writing, explain to the maintainer how the write path avoids
      damaging files
- [ ] **Quality task (first thing to do in this phase):** on 5 neutral files,
      compare `qwen2.5-coder:1.5b`, `qwen2.5-coder:7b`,
      `deepseek-coder-v2:16b` and `qwen3-coder:30b`. Record per model:
      seconds per file, tok/s, share of pieces rejected by Argus, number of
      trivial or wrong comments
- [ ] Decide the open output-mode question (§2): *full-rewrite* vs
      *docstring-only*. Note for the decision: on this CPU, generation speed is
      ~16–27 tok/s, so **output length dominates total time**. Docstring-only
      mode produces far fewer output tokens and cannot alter code by
      construction; full-rewrite allows inline comments but costs more time and
      relies entirely on Argus
- **Done when:** on `examples/retry.py` it yields a diff containing only the
  docstring, with both models

---

## 10. Phase F — Review with the strong model (`momus review`)

- [ ] `critic.py`: builds a **compact diff of the comments only** (with the
      function body next to the comment for important functions, so a
      well-written false comment cannot fool the reviewer) and sends it to the
      strong backend
- [ ] Required output, short: `file:line: problem` per false, redundant or
      inconsistent comment. No summaries
- [ ] Backends:
  - [ ] `anthropic.py` — `anthropic` SDK, key from an environment variable,
        never in code or config files
  - [ ] `claude_code.py` — non-interactive `claude -p` call
  - [ ] Backend chosen in `momus.toml`
- [ ] Work in batches (e.g. every 5–10 touched files), not after every edit
- [ ] A fake backend for tests so the test suite never calls a real API
- **Done when:** `momus review` works with at least one real backend and with
  the fake one in tests

---

## 11. Phase G — Benchmark (`momus bench`)

- [ ] Table per model: seconds per file, tok/s, % of pieces accepted by Argus,
      number of comments flagged by the reviewer
- [ ] Main metric: **comments accepted by Argus ÷ time spent**
- [ ] Record the measurement conditions listed in §3
- [ ] Save raw results in `benchmarks/`, summarize in the README **including
      failures**
- [ ] Optional later: add `granite4:3b` once a download is possible
- [ ] If the 30B is too slow to run the whole benchmark, say so in the table
      (e.g. run it on fewer files) instead of silently dropping it
- **Done when:** one reproducible table covering `qwen2.5-coder:1.5b`,
  `qwen2.5-coder:7b`, `deepseek-coder-v2:16b` and `qwen3-coder:30b`

---

## 12. Phase H — README, logo, publication

- [ ] README in English: what it is, flow diagram, before/after example,
      install, usage, benchmark table, known limits, model-license note (no
      weights in the repo)
- [ ] Tell the allegory: Clio writes, Argus watches, Momus criticizes
- [ ] Logo: Greek theatrical mask of Momus with a magnifying glass over one
      eye, flat vector style, thick lines, purple on black, to be converted to
      ASCII art. Note: dark purple on black has very low contrast and the ASCII
      converters work on luminance — generate with a brighter purple (e.g.
      `#8A2BE2`), convert, then color the text dark purple, or raise contrast
      before converting
- [ ] Before publishing: check the `momus` name on GitHub, check no secrets in
      git history, choose a license (propose options)
- **Done when:** the repo is public with a README a stranger can follow

---

## 13. Open questions

- [ ] Repo name: is `momus` too crowded on GitHub? Fallbacks: `momus-docs`,
      `momus-cli`
- [ ] License for the repo (MIT / Apache-2.0 / other) — to propose
- [ ] Output mode for Clio (§2, §9)
- [ ] Final default model — decided by the benchmark, not by guesswork
- [ ] Which review backend to demonstrate first: Anthropic API (pay per token)
      or Claude Code (subscription, no key)

---

## 14. Quality rules (invariants)

- Every module has tests; the AST guard is the critical part and gets the most
- **No stage ever modifies code, only comments and docstrings**
- Estimates not yet measured are labeled as estimates, also in the README
- Fail closed: if anything is unparseable or ambiguous, discard the output and
  leave the original file untouched
- When asked to run something, give one command at a time, with an explanation

---

## 15. Cross-section execution order (added 2026-11-09)

> Orders work across phases, given the current state (nothing built yet, models
> already installed, slow connection). Re-evaluate at the recheck checkpoint
> rather than assuming it is still right.

**Order**

- [ ] 1. §5 — skeleton, `.gitignore`, first commit
- [ ] 2. §6 — local backend talking to `qwen2.5-coder:1.5b`
- [ ] 3. §7 — Argus with tests (before any file is written by a model)
- [ ] 4. §8 — cleaning and splitting
- [ ] 5. §9 — Clio, including the quality comparison and the output-mode decision
- [ ] 6. §10 — review stage with a fake backend first, then a real one
- [ ] 7. §11 — benchmark
- [ ] 8. §12 — README, logo, publication

**Recheck — every 2 work sessions**

- [ ] Did anything built in the last two sessions change what is actually next
      (a bug found, a decision reversed, something harder or easier)?
- [ ] Is anything now blocking that was not before (e.g. the quality comparison
      showing none of the four models passes Argus often enough)?
- [ ] Does the goal still hold — a portfolio-grade repo with an honest
      benchmark? If the large models are too slow and the 1.5B and 7B too
      poor, decide deliberately whether to try another model (e.g.
      `granite4:3b`) rather than drifting

If nothing has changed, continue down the list without a full replan.

---

## 16. Later ideas (not committed)

- [ ] Pre-commit hook that runs `comment` + `guard` on staged files
- [ ] A Claude Code skill or MCP wrapper around the CLI
- [ ] Support for languages other than Python (needs a non-`ast` guard, e.g.
      tree-sitter)
- [ ] Cache: skip pieces whose code hash has not changed since the last run