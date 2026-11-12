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
- Reference state for the latest update of this plan: **pre-v0.1.0, §5–§8
  built (skeleton, local backend, Argus, cleaning, splitter); no Clio yet**.
  Last updated **2026-11-12**
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

Planned CLI: `momus comment`, `momus guard`, `momus review`, `momus bench`,
`momus daemon {start,stop,status}` (background mode — see §16.7),
`momus restore <file>` (undo, see §16.7).

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
- [x] **Output mode for Clio: docstring-only** — decided 2026-11-11 by the
      maintainer (see §9): the model returns only the docstring text and Momus
      inserts it programmatically, instead of *full-rewrite* (model returns the
      whole code, Argus verifies). The earlier plan was to decide after the
      first quality comparison; that comparison still runs, and the choice is
      reconsidered only if it shows a problem. This mode alone gives docstrings
      only; inline `#` comments are covered by the anchoring decided in §9
- [x] **A separate settings app is part of the product** — decided 2026-11-10:
      a small, standalone app to change configuration (backend/model choice per
      stage, endpoints, and GPU settings — see §3a and §16) independent of the
      pipeline's own code: the CLI only reads the shared config file, the
      settings app only writes it, neither imports the other
- [x] **Settings app scope expanded** — decided 2026-11-11: beyond editing
      `momus.toml`, it covers Ollama configuration and model selection, the
      Claude API connection for the review stage, Ollama **Modelfile**
      management (temperature, context limit, GPU/resource parameters, system
      prompt, all tied to a named local-model configuration), multiple named
      configuration **profiles** (not just one live config), and an
      appearance setting (light/dark, Braun-inspired black-and-white visual
      style). Full detail in §16
- [x] **Background mode is a pipeline feature, not a settings-app feature** —
      decided 2026-11-11: once the review backend is configured, Momus can run
      as a background daemon, started/stopped from Claude Code chat via
      `/activate_momus` and `/deactivate_momus`. The settings app configures
      what the daemon uses; it does not run it. Decided so far: a filesystem
      watcher triggers it, it writes comments on its own (only output that
      passed Argus), and Claude Code reviews them afterwards, every N or on
      demand with `/momus_check`. Activation counts as consent to write
      (CLAUDE.md still has to be updated), N means comments written, undo is
      a backup copy, results go to a report file. Defaults decided
      2026-11-12 (N = 50, wait = 30 s, last 5 backups per file). Still open:
      how a restore is triggered — see §16.7
- [x] **The app is also a models space and a usage space** — decided
      2026-11-11: its home view shows the models that are running (§16.9), and
      a dedicated space shows, per project, numbers and no charts: theoretical
      tokens saved (an estimate), tokens consumed, speed and other values
      (§16.10). The pipeline writes a counts-only usage
      ledger; the app only reads it. Bug-hunting stays out of scope for now
      (§17)
- [x] **The settings app is a desktop app, not a web app** — decided
      2026-11-11: it opens as a window on the maintainer's machine, built
      with Qt Widgets (§16.1). On opening it must sync at once with what is
      already running (§16.9)

> **Note**: the repo license is MIT (decided 2026-11-12, §13); the LICENSE
> file is still to be added (§12). Model
> weights are never shipped in the repo; the README only says how to download
> them and links to their licenses.

---

## 3. Environment and measured baseline

**Machine**: ThinkPad L14 Gen 1, Ryzen 5 4650U Pro, 32 GB RAM, Linux Mint,
1 TB SSD.

**Update 2026-11-10**: a dedicated GPU is now available as well — exact
model/VRAM **not recorded yet** (fill in here once confirmed: `nvidia-smi` or
equivalent). Until models are actually re-benchmarked on it, treat every
number in this section as CPU-only: nothing below has been measured with GPU
acceleration, so "it'll be faster on the GPU" stays an expectation, not a
result, until §3a below is filled in with real numbers.

The pipeline was designed as a **batch job** (launch and do something else
meanwhile), not an interactive tool, on the assumption of CPU-only inference.
That assumption doesn't flip back to "interactive" just because a GPU exists
now — revisit it deliberately, with real GPU timings in hand, rather than by
default.

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
2026-11-09, **CPU only**):

| | deepseek-coder-v2:16b | qwen2.5-coder:1.5b |
|---|---|---|
| Generation | 16.3 tok/s (cold), 17.3 tok/s (warm) | 27.4 tok/s (cold) |
| Load time | 11.5 s (cold), 0.1 s (warm) | 2.0 s (cold) |
| Prompt eval | **unreliable** | 89 tok/s (cold) |
| Total | 18.4 s (cold), 6.7 s (warm) | 7.5 s |

- [x] Ollama installed and both models respond — verified 2026-11-09
- [x] First throughput numbers collected — 2026-11-09 (1.5B and 16B only, CPU)
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
- [ ] Re-run the table above with GPU acceleration once §3a is filled in, and
      keep both tables (CPU and GPU are different, comparable baselines, not a
      replacement of one by the other)

> **Measurement conditions to record in every benchmark**: mains power vs
> battery, power profile, model + quantization, Ollama version, whether the
> model was cold or warm, close other heavy applications, **and now: CPU-only
> vs GPU-accelerated, plus GPU layer-offload setting if applicable**.

### 3a. GPU — not yet filled in (opened 2026-11-10)

- [ ] Record GPU model, VRAM, and driver/CUDA (or ROCm) version here
- [x] **How Momus recognizes the GPU** — decided 2026-11-11 by the
      maintainer: it runs **all three** automatic checks, not stopping at the
      first answer, and compares them. **Not verified**: this environment has
      no GPU, so none of it has run. Read-only, no administrator rights, no
      new dependency:
      1. a vendor tool when present: `nvidia-smi` (NVIDIA) or `rocm-smi`
         (AMD) report name and memory
      2. `lspci` and the files under `/sys/class/drm/`, which give vendor and
         model without a driver
      3. Ollama itself: `ollama ps` (and its running-models endpoint, §16.9)
         shows how much of a loaded model sits on the GPU, but as far as I
         know not the GPU's name, so it confirms use rather than identity
- [x] **When the GPU is not recognized** — decided 2026-11-11: the settings
      app shows what each check found, and the maintainer can edit the GPU
      entry by hand; the entry made by hand overrides detection. The same
      applies when the checks disagree. The value is stored together with its
      source ("detected" or "entered by hand"), and the benchmark's
      measurement conditions record it
- [ ] First action, for the maintainer on the laptop: run
      `lspci | grep -i -E "vga|3d|display"` and paste the output. As far as I
      know the Ryzen 5 4650U has integrated Radeon graphics; whether that is
      the GPU now available, or a separate one, I do not know. Whether Ollama
      can use this kind of GPU is **not checked**
- [ ] Confirm Ollama is actually using it (`ollama ps` shows `100% GPU` for a
      loaded model, not a CPU/GPU split) rather than assuming a GPU present
      means a GPU used
- [ ] Re-run the §3 benchmark table on the GPU, same models, same conditions
      otherwise, and record it as its own table — do not overwrite the CPU one
- [ ] Decide whether the CPU-only "batch job, not interactive" framing (§3)
      still holds once real GPU numbers are in, or whether a faster path
      changes that for some models

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
├── assets/               # logo
├── .claude/
│   └── commands/
│       ├── activate_momus.md    # wraps `momus daemon start` — see §16.7
│       ├── deactivate_momus.md  # wraps `momus daemon stop` — see §16.7
│       └── momus_check.md       # on-demand review of unreviewed comments — §16.7
└── settings-app/         # independent of src/momus/ — see §16
    ├── app.py
    ├── schema.py
    ├── config_io.py
    ├── modelfiles/        # saved Ollama Modelfiles, one per profile (§16.4)
    ├── profiles/          # saved named momus.toml variants (§16.5)
    └── ui/                # Qt interface, light/dark + Braun-style tokens (§16.1, §16.8); layout depends on Widgets vs QML
```

> `src/momus/` also gains a `daemon.py` (or `watcher.py`) module for the
> background mode itself (§16.7) — that module is pipeline code, not part of
> `settings-app/`, even though it's configured through it. The code that
> writes the usage ledger (§11, §16.10) is pipeline code too; the settings
> app only reads the file.

---

## 5. Phase A — Project skeleton

- [x] `git init` and virtual environment in the project folder — verified
      2026-11-09 (`git status`, `.venv/bin/python --version`)
- [x] `.gitignore` covering `.venv/`, `__pycache__/`, `*.gguf`,
      `*.safetensors`, `.env`, `.env.*`, `*.key`, `config.local.*`, editor
      files — verified 2026-11-09 with `git check-ignore -v`; `.venv/` is not
      listed in `git status`
- [x] `pyproject.toml` (Python 3.11+), `src/momus` package, CLI with `--help`
      and empty subcommands — verified 2026-11-09 (`momus --help`; each
      subcommand exits 1 with "not implemented yet")
- [x] Smoke test that imports the package — `tests/test_smoke.py`, 7 passed
- [x] `requirements.txt` / `requirements-dev.txt` (added 2026-11-09, via the
      `deps-sync` skill). Checked with `pip install --dry-run` only; a clean
      install in a fresh venv was **not** run
- **Done when:** `momus --help` works and `pytest` passes — met 2026-11-09

---

## 6. Phase B — Local backend

- [x] Common backend interface: one function that takes a prompt and returns
      text; all backends implement it — `Backend` protocol in
      `backends/__init__.py`, plus `FakeBackend` for tests (2026-11-10)
- [x] `backends/local.py`: client for the local server — plain HTTP with the
      standard library (`urllib`), chosen by the maintainer 2026-11-10: no new
      dependency for a single JSON request
- [x] Parameters read from `momus.toml`: base URL, model name, temperature
      (default 0), optional `max_tokens`, timeout. **Context size is not in the
      file**: `/v1` ignores it per request (checked once on Ollama 0.23.3: an
      `options.num_ctx` field was ignored and the context stayed at 4096), so
      it is set on the server (`OLLAMA_CONTEXT_LENGTH` or a Modelfile). The
      maintainer chose `/v1` so the backend stays portable and Ollama stays
      user-customizable
- [ ] **Added 2026-11-10**: GPU-related server settings (which device(s) to
      use, how many layers to offload, a VRAM budget) are **not** read from
      `momus.toml` today — they live on the Ollama server side
      (`OLLAMA_NUM_GPU`, `num_gpu` in a Modelfile, `CUDA_VISIBLE_DEVICES`, etc.).
      Decide in §16.4/§16.6 whether the settings app only *displays* these
      (read-only, since they're server config, not per-request) or can also
      *write* them (e.g. by editing a Modelfile and asking Ollama to reload) —
      do not assume either way yet
- **Done when:** a script calls `qwen2.5-coder:1.5b` and prints the answer —
  met 2026-11-10 (also tried `qwen2.5-coder:7b` and `deepseek-coder-v2:16b`;
  `qwen3-coder:30b` not tried yet)

---

## 7. Phase C — Argus (AST guard), built before Clio

- [x] `argus.py`: a function taking original code and new code and returning
      whether the **code** is identical — `compare_code()` returns a
      `Verdict(accepted, reason)` and never raises (done 2026-11-12, 59 tests
      green in the whole suite)
- [x] Method: parse both with Python's `ast`, remove docstrings (module, class,
      function, async function), compare `ast.dump` without attributes. `#`
      comments are not in the AST, so they are already ignored
- [x] Edge cases to handle explicitly:
  - [x] A function whose body is only a docstring becomes empty after removal —
        normalize to `pass` on both sides
  - [x] Ordinary string literals that are **not** docstrings must **not** be
        ignored
  - [x] Unparseable new code → discard (fail closed). Also discarded: an
        unparseable original, non-text input, a null byte, and code nested
        too deeply for the parser or for `ast.dump`
  - [x] Never ignore f-strings or other string-like expressions
- [x] Tests in `tests/test_argus.py`:
  - [x] same code + docstring added → accepted
  - [x] renamed variable → discarded
  - [x] line of code added or removed → discarded
  - [x] string literal changed → discarded
  - [x] invalid output → discarded
  - [x] same code + `#` comment added (inline comments are in scope since
        2026-11-11, §9) → accepted
  - [x] the tuple `(1,)` changed to `(1)` → discarded (checked 2026-11-11:
        `ast.dump` tells them apart)
- [x] **Added 2026-11-11 — what Argus does not see, and the second check.**
      Checked by running `ast.dump` on small examples (2026-11-11): spacing
      (`x=1` vs `x = 1`), quote style, redundant parentheses, line wrapping
      and a trailing comma in a call all give the **same** dump. So a
      comparison on `ast.dump` alone would accept an output that reformatted
      the code, which goes against "code is never modified". Since Momus now
      inserts docstrings and comments itself (§2, §9), it knows exactly which
      lines it added. Decided 2026-11-11: a second check in the
      same module — removing the lines Momus inserted from the new text must
      give the original text **byte for byte**. If it does not, the output is
      discarded. This is stricter than the AST comparison and shares its
      fail-closed rule — built 2026-11-12 as `check_inserted_lines()`, 90
      tests green in the whole suite. **Not wired into the pipeline yet**
      (that happens in §9)
- [x] Build order inside this phase (2026-11-11, followed 2026-11-12): first the core comparison
      with its tests (the items above, up to the `(1,)` test); then the second
      check as a **pure function** that receives the original text, the new
      text and the numbers of the inserted lines. It can be built and tested
      now without the insertion step of §9, which does not exist yet; it is
      wired in during §9
- [ ] Design note for later phases (first half done 2026-11-12: the shared
      normalization is `normalized_tree()` / `code_fingerprint()` in
      `argus.py`): the fingerprints and position checks of
      §9 reuse the same parsing and normalization as Argus. Keep that
      normalization in one place that both can call. Whether the §9 checks
      live in `argus.py` or in a separate module is **not decided**
- [ ] Argus does not enforce ownership (§16.7): a replaced existing docstring
      passes the AST comparison. Not replacing comments Momus does not own is
      the job of Clio's insertion step (§9)
- **Done when:** all tests pass and the maintainer can explain the logic in
  plain words

---

## 8. Phase D — Output cleaning and file splitting

- [x] `cleaning.py`: strip markdown fences (```), leading/trailing chatter
      ("Here is the code…"), `<think>` blocks if a reasoning model is used. Tests
      — `clean_output()`, done 2026-11-12. Chatter is removed only when a
      fence marks where the answer is; a sentence glued to an unfenced answer
      is left for Argus to reject. Tested on written examples only, **not on
      real model replies**
- [x] `splitter.py`: split a file into top-level functions and classes using
      `ast` line numbers (`lineno`/`end_lineno`; include decorators); large
      classes can be split per method. Each model request stays small —
      `split_source()`, done 2026-11-12. Per-method splitting is opt-in
      (`max_class_lines`); the threshold to use is **not decided** (§9)
- [x] Verify that reassembling the untouched pieces reproduces the original file
      byte for byte — tested on 9 sources (CRLF, no final newline, empty file,
      form feed) in both splitting modes; the splitter also checks it on every
      call and raises `SplitError` otherwise
- **Done when:** tests on a file with several functions, including decorators
  — met 2026-11-12 (134 tests green in the whole suite)

---

## 9. Phase E — Clio (`momus comment`)

- [ ] Reads the given files or the modified ones (`git diff --name-only`),
      splits them, sends each piece to the local model, cleans the output,
      passes it to Argus
- [ ] (Docstring slice built 2026-11-12: `src/momus/prompts/clio.txt`; the
      prompt for inline comments does not exist yet.) Prompt in English, kept
      in a **separate, easily editable file**. Intent:
      "Add concise docstrings and comments explaining WHY, not what. Do not change
      any code. Output only the code."
- [x] Safe behavior: **dry-run by default** (show diff, write nothing);
      `--write` applies. Pieces rejected by Argus stay untouched and are listed
      — built 2026-11-12 for the **docstring slice** (`momus comment FILE`).
      Dry-run checked on `examples/retry.py` with two real models (file
      unchanged afterwards); `--write` checked only with the fake backend on
      temporary files, **never yet on a real model run**
- [ ] Before writing, explain to the maintainer how the write path avoids
      damaging files
- [ ] **Quality task (first thing to do in this phase):** on 5 neutral files,
      compare `qwen2.5-coder:1.5b`, `qwen2.5-coder:7b`,
      `deepseek-coder-v2:16b` and `qwen3-coder:30b`. Record per model:
      seconds per file, tok/s, share of pieces rejected by Argus, number of
      trivial or wrong comments. The 5 files were written 2026-11-12 in
      `benchmarks/samples/` (`stats`, `inventory`, `async_tools`,
      `report_lines`, `text_tools`); `report_lines.py` already has docstrings
      and comments written by hand, to test the ownership rule. The comparison
      itself has **not been run**
- [x] Output mode decided 2026-11-11 (§2): **docstring-only**. The model
      returns only the docstring text; Momus finds the right place with `ast`
      line numbers and inserts it itself. Reason on this CPU: generation speed
      is ~16–27 tok/s, so **output length dominates total time**, and
      docstring-only produces far fewer output tokens (expected, not yet
      measured). Argus still checks every result: inserting by program does
      not make the guard optional
- [x] **Inline `#` comments: option (b)** — decided 2026-11-11 by the
      maintainer. Docstring-only gives docstrings, not comments inside
      function bodies, and the project's goal mentions both. So the model
      returns pairs of (statement to anchor on, comment text) and Momus
      inserts them. Option (a), docstrings only in v1, was not chosen. What
      is still open is how well this works: it depends on the anchors below
      and on whether the local models follow the format, **not yet tested**.
      The quality comparison measures it, and (b) is reconsidered only if it
      shows a problem
- [ ] Statement anchors by hash (idea from the maintainer, 2026-11-11) —
      the mechanism for (b); accepted 2026-11-12, with the open details below:
      - Momus numbers the statements of a piece itself (S1, S2, …) and shows
        the model the code with those numbers; the model answers "S3: comment
        text". The model never sees or produces hashes. Whether a local model
        follows this format reliably is **not tested**; the quality comparison
        would measure how many answers point at a valid statement
      - For each statement Momus takes a fingerprint of its code as Python
        parses it (`ast.dump` without positions, the same material Argus
        compares), so it ignores comments and formatting and does not depend
        on the line number
      - After inserting, Momus checks both things: the sequence of statement
        fingerprints is the same as before (code unchanged, a stronger form of
        Argus's check), and each comment sits directly above the statement it
        was meant for (position check)
      - Later, the same fingerprints let Momus find "its" comment again after
        lines have moved, and notice that the code under it changed, which
        marks the comment as possibly stale without asking a model
      - Checked on a small example 2026-11-11 (not yet in tests): inserting a
        comment moved a statement from line 2 to line 3 and left its
        fingerprint unchanged; changing the code changed it; two identical
        statements (`return None` twice) got the **same** fingerprint, so the
        anchor also needs an occurrence number or the previous statement's
        fingerprint
      - Identical statements — proposed by the maintainer, 2026-11-11, and
        accepted: when
        two statements have the same fingerprint, Momus also looks at the
        fingerprints before them and how they relate (the chain of preceding
        statements) until the anchor is unique. Known limits, **not yet
        designed**: the first statement of a function has no predecessor (the
        function's qualified name can serve); a run of identical statements
        stays ambiguous however far back Momus looks, so an occurrence number
        is still needed; and if a preceding statement is edited, the anchor
        of a later one stops matching, so ownership is lost more often (the
        safe direction). How many predecessors to use is to be decided with
        real examples
      - Open details: compound statements (`if`, `for`) include their whole
        body in the fingerprint, so a header-only fingerprint may be needed;
        finding existing comments needs Python's `tokenize`, because `ast`
        does not contain comments; and the fingerprints stored in the record
        may stop matching if the Python version changes how `ast` prints
        nodes (not verified), which would drop ownership, the safe direction
- [ ] An existing docstring or comment that Momus does not own is never
      replaced (§16.7, ownership): where one exists, Clio skips that piece
- **Done when:** on `examples/retry.py` it yields a diff containing only the
  docstring, with both models — docstring half met 2026-11-12 in dry-run with
  `qwen2.5-coder:1.5b` and `qwen2.5-coder:7b` (the diff is one inserted
  docstring, nothing else). Quality is weak, see `WORKLOG.md`; inline comments
  (slice 2) and the four-model comparison are still to do

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
- [ ] Record the measurement conditions listed in §3 (CPU/GPU included)
- [ ] Save raw results in `benchmarks/`, summarize in the README **including
      failures**
- [ ] Usage ledger (added 2026-11-11, feeds §16.10): each Clio and review call
      appends one counts-only record (tokens in/out, outcome) to a file in the
      Momus data folder (§16.7). No code or comment text in it. The same records give the
      benchmark its token columns
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
- [ ] Before publishing: the `momus` name was checked on GitHub on 2026-11-12
      (result in §13; the final decision is the maintainer's), check no
      secrets in git history, add the MIT LICENSE file (decided 2026-11-12)
- **Done when:** the repo is public with a README a stranger can follow

---

## 13. Open questions

- [ ] Repo name: is `momus` too crowded on GitHub? Fallbacks: `momus-docs`,
      `momus-cli`. Checked 2026-11-12 through the GitHub API: 39 repositories
      are named exactly `momus`. I looked at the first 12 by stars and at
      their descriptions: the most starred are `LevyHsu/Momus` (12 stars,
      image obfuscation) and `rickdotnet/Momus` (11 stars, a reverse proxy);
      the others are in unrelated areas or have no description, and none is a
      tool for code comments. On PyPI, `momus` and `momus-cli` returned
      "not found" (404), so both names look free today. **Not checked**: the
      repos without a description, other platforms, trademarks. The
      maintainer decides whether this is little enough confusion; fallbacks
      stay available
- [x] License for the repo: **MIT** — decided 2026-11-12. As far as I know it
      is compatible with PySide6 (LGPL) used as a library; not legal advice.
      The licenses of everything that ships are checked again at packaging
- [x] Output mode for Clio (§2, §9) — decided 2026-11-11: docstring-only.
      Inline `#` comments: option (b), anchored by statement (§9)
- [ ] Final default model — decided by the benchmark, not by guesswork
- [ ] Which review backend to demonstrate first: Anthropic API (pay per token)
      or Claude Code (subscription, no key)
- [x] Daemon trigger for §16.7 — decided 2026-11-11: filesystem watcher
      (e.g. `watchdog`). Debounce and ignore rules still to define in §16.7
- [x] §16.4/§16.6 — decided 2026-11-11: the settings app only *generates*
      Modelfiles; it never calls `ollama create` (no subprocess access to
      Ollama). The maintainer applies the file by hand
- [x] §16.8 — decided 2026-11-11: theme preference in a small settings file
      of the app's own (replaces the earlier `localStorage` choice, which
      assumed a browser)
- [x] §16.7 — decided 2026-11-11: `/activate_momus` is the consent to write;
      review every N comments written or on demand; backup copy for undo; a
      report file for results; data folder outside the projects
- [ ] §16.7: the exception still has to be copied into the repo's own
      CLAUDE.md (an updated copy exists), and how a restore is triggered is
      not decided

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

- [ ] 1. §5 — skeleton, `.gitignore`, first commit (skeleton and `.gitignore`
      done 2026-11-09; the skeleton commit waits for the maintainer's request)
- [x] 2. §6 — local backend talking to `qwen2.5-coder:1.5b`
- [ ] 3. §7 — Argus with tests (before any file is written by a model) —
      built and tested 2026-11-12; open only for §7's "maintainer can explain
      the logic"
- [x] 4. §8 — cleaning and splitting
- [ ] 5. §9 — Clio, including the quality comparison and the output-mode decision
- [ ] 6. §10 — review stage with a fake backend first, then a real one
- [ ] 7. §11 — benchmark
- [ ] 8. §12 — README, logo, publication
- [ ] 9. §16 (settings app) — after the core CLI works end to end, not before:
      the config schema is easiest to get right once Clio/Argus/Momus have
      actually used it for a while. Internal order within §16:
      9a. §16.1 architecture decisions (lock the config-file-as-contract
          boundary before writing any settings-app code)
      9b. §16.2 Ollama configuration & model selection, together with
          §16.3 Claude API connection (the two "which backend, which model"
          screens — natural to build side by side)
      9c. §16.5 named configuration profiles (needs 16.2/16.3 to exist first,
          since a profile is a saved bundle of those settings)
      9d. §16.4 Modelfile management (depends on knowing which local model/
          profile is active)
      9e. §16.6 resource & generation-parameter UI (temperature, context
          limit, GPU/resources — writes into the same Modelfile from 16.4)
      9f. §16.7 Claude Code integration — background activation
          (`/activate_momus`, `/deactivate_momus`, `/momus_check`; needs a working review
          config from 16.3 to have anything to activate)
      9g. §16.9 models space (needs the Ollama connection from 16.2; the
          daemon status part waits for 16.7)
      9h. §16.10 usage space (needs the usage ledger from §11 to exist
          and to have real records in it)
      9i. §16.8 appearance (lowest risk, purely cosmetic — last, can slip
          without blocking anything else; the numbers in 16.10 should follow it)

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

## 16. Settings app (promoted from idea to planned phase, 2026-11-11)

> Scope expanded per the 2026-11-11 decision in §2. Sequenced after the core
> pipeline works end to end — see §15, step 9, for *why* and for the internal
> build order across 16.1–16.8 below. Nothing in this section is built yet;
> every `[ ]` here is unstarted, and every open mechanic is flagged
> explicitly rather than assumed.

**Hard boundary (do not relax while implementing any of 16.1–16.10):** the
settings app and the Momus CLI/daemon never import each other's code. They
agree only on the `momus.toml` schema (and, for Modelfiles, the files under
`settings-app/modelfiles/`). The CLI/daemon only ever *reads* these files at
startup (and on daemon-reload, once §16.7 defines what that means); the
settings app is the only thing that *writes* them. This is the same
config-file-as-contract rule already used for Clio/review backend settings
— GPU and Modelfile settings do not get an exception.

The contract also has a reverse direction, added 2026-11-11 for §16.9 and
§16.10: the pipeline *writes* a usage ledger (and, if §16.9 needs it, a daemon
status file) and the settings app only ever *reads* them. Still files, never
imports. Besides settings, the app is now also a **models space** (what is
running, §16.9) and a **usage space** of numbers (§16.10); the folder stays
`settings-app/` until the maintainer decides to rename it.

### 16.1 Architecture decisions

- [x] Settings app lives in its own top-level `settings-app/` folder (§4) —
      decided 2026-11-10
- [x] Settings app only ever writes `momus.toml` (and Modelfiles); the
      CLI/daemon only ever reads them — decided 2026-11-10, reaffirmed
      2026-11-11 for the expanded scope
- [ ] API keys never get written to `momus.toml` or any Modelfile — the
      settings app reads `ANTHROPIC_API_KEY` from the environment to display
      connection status, but never persists the key itself (hard rule,
      carried over from CLAUDE.md's "never commit API keys" — applies to any
      file this app writes, not only git commits)
- [x] Validation — decided 2026-11-11: basic checks only. Reject non-numeric
      values and clearly absurd ones (e.g. a `num_ctx` far beyond what 32 GB
      RAM can hold); no hardware-derived hard limits in v1
- [x] Desktop app, not a web app — decided 2026-11-11 (see §2)
- [x] **UI technology: Qt** — decided 2026-11-11 by the maintainer. Pywebview
      (a web view in a native window) and Tkinter were considered and not
      chosen. With Qt there is no web view, so no local web server such as
      FastAPI is needed: the app reads and writes the shared files directly
- [x] **Writing TOML** — `tomli-w` approved 2026-11-12. Needed because the settings app and the theme file
      are TOML (2026-11-12): Python's standard library reads TOML (`tomllib`)
      but does not write it, so a writer library is needed, such as `tomli-w`
      (1.2.0, released 2025-01-15, Python >=3.9, no runtime dependencies,
      checked on PyPI). It belongs to the app's optional extra, since only
      the settings app writes TOML; the CLI and daemon only read it, and the
      daemon writes JSON with the standard library. A new dependency, approved;
      I have not checked whether the repo already lists it
- [x] **Qt binding — approved 2026-11-12:** `PySide6-Essentials`.
      Checked on PyPI 2026-11-11 (metadata only; nothing installed): version
      6.12.0, released 2026-10-08, Python >=3.10, licensed LGPL-3.0 or GPL.
      The `PySide6-Essentials` wheel is 84 MB on Linux x86_64. The umbrella
      `PySide6` package additionally pulls `PySide6-Addons` (59 MB),
      WebEngine and Pdf, which this app does not need. Alternative `PyQt6`
      6.12.0 is licensed GPL-3.0 only (or commercially). As far as I know a
      GPL-only dependency would constrain the repo's own license, which is
      MIT (§13), so PySide6 is preferred; this is not legal advice and
      should be checked. Any new dependency needs the maintainer's approval
      (CLAUDE.md)
- [ ] **Dependencies and packaging** — requirement from the maintainer,
      2026-11-11: everything the app needs, including what will be needed to
      package it later, must be listed in `requirements.txt`, so the same list
      can be reused when packaging. The repo already has `pyproject.toml`,
      `requirements.txt` and `requirements-dev.txt` (§5); the two kinds of file
      must not drift apart, and the existing `deps-sync` skill is the
      mechanism used for that (I only know it from §5, not what it does in
      detail). Open points: (a) Qt is 84 MB, so a user who wants only the CLI
      would also install it — whether the app's dependencies go in the same
      `requirements.txt` or in an optional group — answered by the packaging
      decision below; (b) the packaging tool — the wheel was chosen on
      2026-11-11, see below. Per CLAUDE.md, each new dependency still needs approval
- [x] **Packaging: wheel** — decided 2026-11-11 by the maintainer. A Python
      wheel built from the existing `pyproject.toml`, with the Qt app as an
      optional extra (for example `momus[app]`), so CLI-only users do not pull
      Qt. Build tools go in `requirements-dev.txt`. The earlier requirement
      stands: `requirements.txt` lists everything the app needs (§16.1). How
      `deps-sync` keeps `requirements.txt` and the core / `app` split in
      `pyproject.toml` aligned is **not decided**. A standalone executable is
      not chosen; the options below wait until the app exists
- [ ] **Packaging options** (facts from PyPI metadata, 2026-11-11; nothing
      installed or run, and I have not checked how any of them behaves with
      Qt on this machine). Item 1 is the decision above; items 2 and 3 are
      options for a standalone executable, **not chosen**:
      1. A Python wheel built from the existing `pyproject.toml` with the
         PyPA `build` tool (not checked on PyPI today), installed with pip or
         pipx, with the Qt app as an optional extra (for example
         `momus[app]`) so that CLI-only users do not pull Qt's 84 MB. This
         also answers point (a) above as a proposal. Build tools go in
         `requirements-dev.txt`, not in the runtime list
      2. For a standalone Linux executable of the app: `pyside6-deploy`, a
         command that ships inside `PySide6-Essentials` (checked in the
         wheel's entry points), so it adds no dependency of its own. As far as
         I know it builds with Nuitka underneath; **not verified**
      3. Fallback: PyInstaller 6.22.3 (released 2026-09-12), licensed GPLv2 or
         later with a special exception; as far as I know the exception lets
         the bundled app carry any license; not legal advice, to verify
      Not preferred now: Nuitka 4.3.5 (2026-11-08) on its own, because the
      tool is AGPL-3.0 and I have not checked what that means for the repo's
      license; Briefcase 0.4.7 (2026-10-27, BSD-3-Clause), a heavier workflow
      whose Linux formats I have not checked. The decision can wait until the
      app exists
- [x] **Every tunable value is a setting** — decided 2026-11-11: any number,
      threshold, interval or default (review interval N, wait after a save,
      backup retention, refresh interval, which values the usage space shows,
      temperature, context, GPU settings and the rest) is editable in the
      settings app and is not fixed in code. The code ships sensible defaults.
      API keys remain the exception: environment variables only. Values the
      pipeline reads live in `momus.toml`; values only the app uses live in
      the app's own settings file
- [x] **Limits on that rule** — decided 2026-11-11 by the maintainer:
      CLAUDE.md takes precedence over "every value is a setting". Nothing in
      the settings app may weaken a rule written in CLAUDE.md. In practice,
      both Argus checks, dry-run as the default of manual `momus comment`
      and the guard path for every write stay fixed, and API keys never go in
      a config file. If a proposed setting conflicts with CLAUDE.md, CLAUDE.md
      wins and the setting is not offered. The backup-before-write rule is in
      the updated copy of CLAUDE.md, not yet in the repo's own file
- [x] **Qt Widgets** for the interface — decided 2026-11-11 as the starting
      choice (all Python, one language, easier to explain). Reservation: I
      have not checked that Widgets with stylesheets reaches the Braun look
      (flat surfaces, gradients on buttons and panels). The first step is a
      test of one screen; if it falls short, QML is reconsidered
- [ ] Qt needs a system display and platform libraries on the target machine.
      **Not verified** on this Linux Mint laptop

### 16.2 Ollama configuration & model selection

- [ ] Screen to pick, per stage (Clio / review-if-local), which **backend**
      is active (`ollama` / `llamacpp` / `lmstudio` — see `schema.py`'s
      `LocalBackend`) and its base URL
- [ ] Screen to list locally-available Ollama models (via Ollama's own
      `/api/tags` endpoint, not the OpenAI-compatible `/v1` one) and pick
      which one Clio uses
- [ ] Done when: changing the model in the settings app and restarting the
      CLI picks up the new model, with no code change on the CLI side

### 16.3 Claude API connection

- [ ] Screen showing: is `ANTHROPIC_API_KEY` set in the environment (yes/no
      only — never display the key itself, even partially); which review
      provider is selected (`anthropic_api` vs `claude_code`, see
      `ReviewProvider`); which model name to use for review
- [ ] A "test connection" action that makes one minimal real call and reports
      success/failure — in scope for v1 (decided 2026-11-11). It reads the key
      from the environment for that one call and never stores it
- [ ] Done when: the settings app can show, truthfully, whether the review
      stage is currently configured to work, without ever persisting the key

### 16.4 Modelfile management

- [ ] Generate an Ollama **Modelfile** (`FROM`, `SYSTEM`, `PARAMETER`
      lines) from the settings app's own form fields, save it under
      `settings-app/modelfiles/<name>.modelfile`
- [x] Decided 2026-11-11: the settings app **only generates** the file and
      shows the exact `ollama create <name> -f <path>` command for the
      maintainer to run by hand. It never runs that command, so it needs no
      subprocess access to Ollama
- [ ] Done when: a Modelfile generated by the settings app, applied to
      Ollama by hand, produces a model that Clio can call exactly as it
      calls any other named Ollama model

### 16.5 Named configuration profiles

- [ ] Support more than one saved configuration bundle (e.g. "fast-cpu",
      "accurate-gpu"), not just the one currently-live `momus.toml` — each
      profile bundles a backend+model choice (16.2), a Modelfile (16.4), and
      resource settings (16.6)
- [ ] One profile is "active" at a time; switching the active profile
      rewrites `momus.toml` to match it (the CLI still only ever reads one
      file — profiles are a settings-app-side convenience, not a new
      CLI-facing concept)
- [ ] Done when: switching profiles in the settings app changes what the
      next `momus comment` run actually uses, without editing `momus.toml`
      by hand

### 16.6 Resource & generation-parameter UI

- [ ] Primary controls, favored over secondary ones per the maintainer's
      request: **temperature**, **context limit** (`num_ctx`), and
      **resources** (GPU on/off, layer-offload or VRAM budget if the backend
      exposes one, CPU-fallback toggle — see §3a)
- [ ] These write into the Modelfile (16.4) and/or `momus.toml`, whichever
      the parameter actually belongs to — confirm per-parameter which file
      Ollama reads it from before wiring up the form field (do not assume;
      §3a already found that the `/v1` endpoint's per-request
      `options.num_ctx` is silently ignored by Ollama 0.23.3, so the form
      must write to the place that's actually honored)
- [ ] Done when: changing temperature/context/GPU in this UI measurably
      changes Clio's behavior on the same input (a longer context actually
      fits more diff, a lower temperature actually reduces output variance)

### 16.7 Claude Code integration — background activation

- [ ] `/activate_momus` and `/deactivate_momus` as Claude Code slash commands
      (`.claude/commands/activate_momus.md`, `.../deactivate_momus.md`, per
      §4) — thin wrappers around a new CLI subcommand, `momus daemon
      {start,stop,status}` (§1)
- [ ] This is **pipeline code** (`src/momus/daemon.py` or `watcher.py`, per
      §4's note), not settings-app code — the settings app only configures
      what the daemon uses (which backend, which review provider), it does
      not start or stop it
- [x] Trigger — decided 2026-11-11: a filesystem watcher on the repo (e.g.
      the `watchdog` package). Known trade-offs: it misses events while the
      daemon is down, and it costs some CPU at idle on this laptop
- [x] Wait after a save — decided 2026-11-11: a setting in the settings app
      that runs from "immediately" (no wait) up to "after a pause in saves";
      the maintainer chose a setting between those two behaviors. Default
      value: **30 seconds** (decided 2026-11-12, a starting value that has not
      been measured); maximum **not decided**
- [ ] Ignore patterns (`.git/`, non-`.py` files, Momus's own data) are still
      to define. Known issue, **not yet designed**: when the daemon writes a
      comment, the watcher will see that write as a change, so the daemon must
      recognize and ignore its own writes or it will loop
- [x] Writes — decided 2026-11-11 (**reverses** the earlier same-day choice
      that the daemon asks before writing): once activated, the daemon writes
      comments **on its own, without per-file confirmation**, but only for
      output that passed Argus (fail closed, §7). Review happens *after* the
      write, not before
- [x] Conflict with CLAUDE.md — decided 2026-11-11: `/activate_momus` is the
      explicit consent (the equivalent of `--write`) for the background
      daemon, and every manual `momus comment` run stays dry-run by default
- [ ] Write that exception into CLAUDE.md in words — written 2026-11-11 in a
      **copy** of CLAUDE.md delivered to the maintainer (hard rules section,
      plus the CLI line). The repo's own CLAUDE.md is not changed until the
      maintainer replaces it; until then CLAUDE.md and this plan disagree
- [x] Edit check before writing — decided 2026-11-11: the daemon remembers a
      hash of the file as it read it, and before writing checks that the file
      on disk still has that hash. If the maintainer saved again in the
      meantime, the output is discarded rather than overwriting that edit
- [x] Atomic write — decided 2026-11-11: the daemon writes to a temporary
      file and then replaces the original in one step, so a crash cannot
      leave a half-written file. **Not verified**: how editors behave when a
      file they have open changes on disk
- [x] When the comments reach the file — decided 2026-11-11: one write per
      file, after every piece of that file has been processed. Each piece
      accepted by Argus brings its comments; a rejected piece stays as the
      original. The alternative, one write per piece, would change the file
      many times while the maintainer may be editing it, and each write would
      wake the watcher again. §9 also asks that the write path be explained to
      the maintainer before it is built
- [x] **Ownership of the local model's comments** — decided 2026-11-11 (the
      maintainer's direction: the comments written by the local AI belong to
      Momus; my reading and the rules below confirmed the same day): only
      Momus (the daemon or a manual run) may rewrite or remove a comment it
      wrote. Claude's review only reports (file, line, problem); it does not
      edit
- [x] How ownership is recognized — confirmed 2026-11-11: by file,
      the qualified name of the function or class (from `ast`) and a hash of
      the comment text, all stored in the unreviewed record (§16.7), not by
      line number, because lines shift when code above changes. No marker is
      added to the code, so the comments stay clean. Consequence: if the data
      folder is lost, or the repo is cloned elsewhere, every comment counts as
      not Momus's, which is the safe direction
- [x] Hashing — accepted 2026-11-12: SHA-256 from Python's
      standard library (`hashlib`), so no new dependency. The file hash is
      taken on the file's raw bytes. The comment hash is taken on the comment
      text after removing each line's leading and trailing spaces, so
      re-indenting code does not break ownership (checked on a small example
      2026-11-11; not yet in tests)
- [x] Conflict rules — confirmed 2026-11-11:
      - Claude Code (or the maintainer) edits a file while the daemon works on
        it: the hash check discards the daemon's output; the new save wakes
        the watcher and the file is processed again
      - Claude Code or the maintainer edits a comment Momus wrote: its hash no
        longer matches, so that comment is no longer Momus's and Momus never
        touches it again
      - Claude Code changes code under a Momus comment: the comment may become
        stale; because Momus owns it, a later pass may rewrite it. Argus still
        guarantees the code is unchanged
      - Momus never rewrites a comment it does not own: Clio only adds where
        a comment is missing. This is narrower than CLAUDE.md's "add or
        change", which would need rewording if confirmed
      - If Momus cannot prove it owns a comment (renamed function, moved
        code), it leaves it alone
- [x] After-the-fact review — decided 2026-11-11: Claude Code confirms the
      written comments in two ways: (a) automatically every N (interval set
      in the settings app, see below), and (b) on demand with a new slash
      command `/momus_check` (`.claude/commands/momus_check.md`, wrapping the
      review stage over comments written and not yet reviewed)
- [x] Review interval — decided 2026-11-11: "every N" means every N
      **comments written**. N is a setting in the settings app, saved to
      `momus.toml` and read by the daemon. Default: **50** (decided
      2026-11-12), a starting value that has not been measured
- [x] Data folder — decided 2026-11-11: Momus keeps its working files
      (backups, review report, usage ledger, unreviewed record, daemon
      status) in a per-user folder **outside the projects**, organized by
      project folder name. This way Momus never touches a project's repo or
      its `.gitignore`. Location decided 2026-11-12: configuration in
      `~/.config/momus`; backups, report, usage ledger, unreviewed record and
      status in `~/.local/state/momus/<project folder name>`. The code honors
      the `XDG_CONFIG_HOME` and `XDG_STATE_HOME` variables when they are set,
      resolves the paths at run time (no hardcoded path, CLAUDE.md) and adds
      no dependency, so it is a few lines of the project's own code. As far as
      I know this is the standard Linux (XDG) convention; I have not checked
      it in this environment
- [x] Unreviewed record — decided 2026-11-11: an append-only JSON Lines file
      of events ("written", "reviewed") with file, lines and hash, kept in
      the data folder. Accepted 2026-11-12: it holds no code or
      comment text, only locations and hashes, so it cannot leak code; the
      review reads the file itself. Field names **not decided**
- [x] Undo — decided 2026-11-11: before writing, the daemon saves a backup
      copy of the original file in the data folder. Unlike git, this works on
      uncommitted changes. Retention decided 2026-11-12: the last **5**
      versions of each file are kept and older ones are removed (the number is
      a setting). Restore decided 2026-11-12: a command, `momus restore
      <file>`, puts back the backed-up version.
- [x] Restore safety — decided 2026-11-12 (refuse by default, with an explicit
      flag to force): restoring replaces the
      current file with the older one, so any edit made after Momus wrote
      would be lost. So `momus restore` first checks, with the file hash
      (§16.7), that the file on disk is still the one Momus wrote, and refuses
      if it is not, unless an explicit flag forces it. It is also a new
      feature that writes files, so under CLAUDE.md it goes through the guard
      path: Argus can verify that the restored text differs from the current
      one only in comments (this last part accepted 2026-11-12)
- [x] Review results — decided 2026-11-11: the daemon writes the result to a
      report file in the data folder and `/momus_check` shows it in the chat.
      The output stays short: file, line, problem (§10). This does not depend
      on whether a background process can write into the Claude Code chat,
      which I have not verified
- [x] `/deactivate_momus` — confirmed 2026-11-11: stops the watcher
      immediately and discards any Clio output still in flight (nothing is
      written without passing Argus anyway). Comments already written stay on
      disk and remain in the unreviewed record, so `/momus_check` can still
      review them afterwards
- [ ] Done when: `/activate_momus` in a Claude Code chat starts the daemon
      and `momus daemon status` confirms it is running; a saved `.py` file
      gets comments written; `/momus_check` reports on exactly those
      comments; `/deactivate_momus` stops the daemon by whichever rule 16.7
      settles on

### 16.8 Appearance

- [ ] Light/dark toggle in the settings app's own appearance settings
      (switchable, not fixed at install time)
- [ ] Visual style: black-and-white, Braun-inspired — flat, high-contrast,
      restrained; gradients used specifically on buttons and panel
      backgrounds (not on text or borders) to give depth without adding
      color
- [x] Decided 2026-11-11: the theme preference is saved in a small settings
      file of the app's own, **separate from `momus.toml`** (the theme is not
      pipeline configuration, so it stays out of the contract the CLI reads).
      This replaces the earlier `localStorage` choice, which assumed a
      browser. File location: the config folder above (`~/.config/momus`); format decided 2026-11-12: TOML. If the file is
      missing or unreadable, the app starts with a default theme and does not
      fail
- [ ] Done when: toggling the theme changes the whole settings app's look
      immediately, and the choice survives closing and reopening the app

### 16.9 Models space (added 2026-11-11)

> The app's home view is oriented around the models that are running, not
> around a settings form. Settings (16.2–16.6) become sections reached from it.

- [ ] Show the local models currently loaded: name, size, how much sits on GPU
      vs. RAM, context length, and time until Ollama unloads it. Uses
      Ollama's running-models endpoint (`/api/ps`) — **not verified**: I have
      not checked that it exists and returns these fields on the installed
      Ollama (0.23.3). Check with a real call before building
- [ ] Show the models available locally (`/api/tags`, already in 16.2) next
      to the running ones, so loaded vs. merely installed is visible
- [ ] Show the review side: provider, model name and connection status from
      16.3, so the whole pipeline's models appear in one place
- [ ] Show whether the daemon is running. The app cannot import the daemon,
      so the daemon would write a small status file that the app reads —
      location: the Momus data folder (§16.7); format decided 2026-11-12: JSON (small, written by the daemon, read by the
      app). A status file can go stale if the
      daemon crashes, so it should carry a process id and a last-alive
      timestamp, and the app treats an old timestamp as "not running"
- [ ] **Sync on open** (requirement, 2026-11-11): when the app opens, it must
      show what is already running without waiting. Mechanism accepted
      2026-11-12: one snapshot read (Ollama's running models, the
      daemon status file, the ledger records written since the app last
      looked), drawn at once from the last saved state and then refreshed;
      afterwards a light refresh only while the window is visible, paused
      when it is hidden, and no polling of any remote API. Refresh interval
      **not decided**. As far as I know Ollama has no push events, so a
      refresh means asking it again; I have not checked this
- [ ] What "running with Claude" can mean: Claude's models run on Anthropic's
      servers, so the app cannot see them directly. It can show only what
      Momus recorded: review calls in the ledger, the last connection test
      from 16.3, and the daemon status. Whether Claude Code exposes anything
      about its running sessions to a local app has **not been checked**
- [x] Accepted 2026-11-12: read-only in v1 (no load or unload
      buttons), consistent with the 16.4 decision that the app never writes
      into Ollama
- [x] Accepted 2026-11-12: v1 covers Ollama only. I have not
      checked what llama.cpp and LM Studio expose for running models
- [ ] Done when: starting a model in Ollama makes it appear in this view
      after a refresh, with the same size and context Ollama itself reports

### 16.10 Usage space — numbers, no charts (added 2026-11-11, changed the same day)

- [x] No charts — decided 2026-11-11 by the maintainer (replaces the earlier
      plan for charts). A dedicated space of the app shows **numbers, per
      project**
- [x] Values shown, accepted 2026-11-12 (the exact list can still change): theoretical tokens saved (an
      estimate, see below); tokens consumed, local and Claude separately;
      speed (tokens per second of the local model, and time per file); checks
      done by Claude (review calls made, comments reviewed / flagged); and
      pieces accepted or discarded by Argus. Which values appear is itself a
      setting (§16.1)
- [ ] **Usage ledger**, written by the pipeline (not by the app): an
      append-only file with one record per Clio piece and per review call —
      timestamp, project id, stage, model, tokens in/out, outcome (accepted
      by Argus, discarded, number flagged). **Counts only: never source code,
      comment text or file contents**, so a screenshot or a shared ledger
      cannot leak code. Format accepted 2026-11-12: JSON Lines. Location: the Momus data
      folder (§16.7), outside the projects, so no `.gitignore` entry is needed
- [ ] Pipeline side (see §11): the recording code lives in `src/momus/`, and
      writing a record must never be able to fail a run
- [ ] **Tokens saved is an estimate** and is labeled as one everywhere it
      appears (CLAUDE.md: no unverified performance claims); the label reads
      "theoretical tokens saved (estimate)". Definition accepted
      2026-11-12: tokens a strong model would have
      spent doing the commenting itself on the same pieces, minus the tokens
      Claude actually spent on review. The baseline needs a method: either a
      tokenizer count or, better, one measured run of the strong model on a
      sample, done once in §11
- [ ] Where the token counts come from — **not verified**: whether Ollama's
      `/v1` responses carry a usage field on 0.23.3, and whether `claude -p`
      reports usage. The Anthropic API returns usage per response, to confirm
      in the SDK. Where a source is missing, the number is a tokenizer
      estimate and is labeled so
- [x] Project id — decided 2026-11-11: the repo's folder name. No absolute
      machine paths in the ledger. Collisions, decided 2026-11-12: when two
      projects share a folder name, a short suffix from a hash of the path is
      added to the name (for example `api-3f2a`), and only then
- [x] Charting library — dropped with the charts, 2026-11-11: no charting
      dependency (the pygal and Qt Charts options no longer apply). If charts
      are wanted later, they go to §17
- [ ] Style: numbers in a clear typographic hierarchy, following 16.8; every
      estimate carries a visible "estimate" label and every value its unit;
      meaning is never carried by color alone; light and dark both supported
- [x] Unit — decided 2026-11-11: values are kept per run. Decided
      2026-11-12: for the background daemon, one run is one work cycle, from
      the moment it starts after the wait until it has finished the files in
      its queue. The space shows totals per project at the top and a short
      list of the latest runs below, so the change in values is visible
      without charts. How many runs the list shows is a setting
- [ ] Done when: after running the pipeline on two different projects, the
      space shows separate numbers per project, and the numbers for one
      project match a hand sum of the ledger

---

## 17. Later ideas (not committed)

- [ ] Pre-commit hook that runs `comment` + `guard` on staged files
- [ ] A Claude Code skill or MCP wrapper around the CLI
- [ ] Support for languages other than Python (needs a non-`ast` guard, e.g.
      tree-sitter)
- [ ] Cache: skip pieces whose code hash has not changed since the last run
- [ ] **Bug-hunting: out of scope for now** (decided 2026-11-11). A bug report
      is a judgment, unlike Argus's checkable guarantee, and a small local
      model on CPU would give many false positives. Revisit once the project
      has developed
- [ ] Argus reused as a guard for agent runs (checking an agent changed only
      what it was meant to, e.g. only comments). Idea only, after v1; what
      Claude Code hooks allow has not been checked
- [ ] General monitoring of agents run by Claude Code — a different product
      from Momus; not committed