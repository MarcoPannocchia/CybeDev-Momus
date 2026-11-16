# Worklog

Tests run, choices made and why, newest first. Maintained by the `work-log`
skill. User-facing changes are summarized in [CHANGELOG.md](CHANGELOG.md).

## 2026-11-16 — Real run of `momus review --drop` (plan §10)

**Changed**
- `plan-Momus.md`: §10 `--drop` item ticked, routing item says what has and
  has not run for real; §15 "Resume here" updated
- No code and no test changed, so `CHANGELOG.md` has no new line

**Tests**
- Baseline: `.venv/bin/pytest -q` — 366 passed, 1 deselected (integration).
  Nothing in the suite changed afterwards, so it was not run again
- Real run, the recipe of §15: a temporary git repository, an 11-line
  `calc.py` committed (`clamp`, `mean`), then three comments added: a false
  docstring on `clamp` ("Return the square root of value..."), `# Sum the
  numbers.` above `total = sum(numbers)`, and a useful comment about
  `ZeroDivisionError` above the `return`. Command: `momus review calc.py
  --drop --config <repo>/momus.toml`
- Result: exit 0, "removed 2 flagged comment(s)"; the false docstring and the
  redundant comment were gone, the useful comment was still there;
  `argus.compare_code` of the commit against the result: accepted
- Which model: Haiku, one request, 1 880 input and 514 output tokens, cost
  reported by Claude Code $0.0006. Seen by running the same CLI entry point
  from a throwaway script that printed the backend's model and `last_usage`
  after each call (the CLI itself does not print them)
- An earlier run the same day had the redundant and the useful comment on two
  lines touching each other. They were reviewed as one comment, flagged for
  the redundant sentence, and removed together. That is what the code is
  written to do (`find_comments()` joins touching `#` lines into one block),
  not a fault of the reviewer; the run above separates them
- Not run: a file over 200 lines, so the Sonnet side of the routing has still
  never run for real; more than one file; the `anthropic` backend against the
  real API. One run on one tiny file written by the assistant

**Decisions**
- None. The block behaviour is left as it is and reported to the maintainer

**Open / next**
- For the maintainer: should `--drop` on a block of several `#` lines remove
  the whole block (today), or should the reviewer be asked about each line?
  Clio writes one-line comments, so today this only touches hand-written
  blocks
- `momus review` does not say which model handled a file or what it cost
- The list under "Resume here" in `plan-Momus.md` §15; first on it is
  `momus guard`
- Uncommitted: `plan-Momus.md`, `WORKLOG.md`

## 2026-11-14 — Reviewer model by file size, `momus review --drop`; state at the end of the session (plan §10)

**Where things stand**
- Everything is committed (last commit `33e24ea`); the working tree was clean
  before this entry was written. `.venv/bin/pytest`: 366 passed, 1 deselected
- The pipeline runs end to end from the command line: `momus comment`
  (docstrings by default, `--mode both` for inline comments, `--write` to
  write), `momus review` (`--base`, `--drop`), `momus bench`. `momus guard` is
  still a placeholder
- To continue: `plan-Momus.md` §15, "Resume here"

**Changed**
- `src/momus/critic.py`: `review_routed()`, `drop_flagged()`; `Finding` gained
  `end_line`
- `src/momus/config.py`: `ReviewSettings.model` now defaults to `sonnet`; new
  `small_model` (`haiku`) and `small_file_lines` (200);
  `build_small_review_backend()`
- `src/momus/cli.py`: `momus review --drop`; routing wired in
- `src/momus/backends/claude_code.py`: on a failed call, the reason Claude Code
  gives in its JSON is shown (it was cut off at 300 characters before)
- `momus.toml`: the `[review]` table shows the three settings
- `tests/test_critic.py`: routing, drop and error-reason tests
- `plan-Momus.md` §0, §10, §15; `CHANGELOG.md`

**Tests**
- Baseline before changes: 350 passed, 1 deselected. After: 366 passed, 1
  deselected (integration). Fake backends and a fake process runner only
- Mutation check by hand, four deliberate bugs (routing inverted, drop leaving
  the last line of a comment, drop not checking a finding against its comment,
  files rewritten without `--drop`): each caught
- **Real run of `momus review --drop`: failed, not a pass.** Temporary git
  repository, a 9-line file with a false docstring, a redundant comment and a
  good comment. `claude` exited with status 1: "You've hit your monthly spend
  limit" (HTTP 429; the message gave a reset time of 1:20am Europe/Rome for the
  5-hour limit). Momus printed the failure, wrote nothing (the file still had
  all three comments) and exited 1. So the failure path is confirmed for real;
  the success path of `--drop` and the routing have **never** run against the
  real reviewer
- Not run: `--drop` with a real reviewer answering; routing with real models;
  any file over 200 lines; the `anthropic` backend against the real API;
  Python versions other than 3.12.3

**Decisions**
- Sonnet for long files, Haiku for short ones — decided by the maintainer. In
  the experiment of the entry below Haiku caught the same false docstrings as
  Sonnet, on files under 50 lines
- The threshold of 200 lines, and counting lines of the new file — assistant's
  choice, a guess with no data behind it; it is a setting
- Routing is off when `small_model` is empty or equal to `model`
- `--drop` — proposed by the assistant, accepted by the maintainer. It removes
  every flagged comment, whatever the reviewer's reason (false, redundant or
  inconsistent). Rewriting a flagged docstring by asking Clio again was the
  alternative and was not chosen: more calls, and it can be wrong again
- A dropped file is checked twice over: `find_comments()` on the result runs
  both Argus checks, and the comments left must be exactly the ones not
  flagged. A finding whose line or text does not match an added comment stops
  the whole file
- With the `anthropic` backend the defaults `sonnet` and `haiku` are not valid
  model names; full names are needed there. Said in `momus.toml`, not enforced
  in code

**Known limits**
- No ownership record yet (§16.7): review, and so `--drop`, covers every
  comment added since the git baseline, including the maintainer's own
- A new, untracked file has no baseline and cannot be reviewed
- The reviewer was measured on 60 docstrings from five small files written by
  the assistant, against the assistant's own answer key

**Open / next**
- The real `--drop` run, once the spend limit has reset (recipe in the plan)
- The list under "Resume here" in `plan-Momus.md` §15
- Uncommitted: `plan-Momus.md`, `CHANGELOG.md`, `WORKLOG.md` (this entry)

## 2026-11-14 — The reviewer on Clio's real docstrings (plan §10)

**Changed**
- `src/momus/backends/claude_code.py`: lean flags (`--strict-mcp-config`,
  `--disable-slash-commands`, own `--system-prompt`), `--output-format json`,
  `last_usage`; errors reported by Claude Code become `BackendError`
- `src/momus/critic.py`: `_mark_omissions()`; `src/momus/prompts/critic.txt`:
  a rule about code shown only in part
- `src/momus/quality.py`: markdown bold removed, more empty entries recognised
- `tests/test_critic.py`, `tests/test_quality.py`
- `plan-Momus.md` §10, `CHANGELOG.md`

**Tests**
- Baseline before changes: 336 passed, 1 deselected. After: `.venv/bin/pytest`
  — 350 passed, 1 deselected (integration). No real model or API in the suite
- Mutation check by hand, five deliberate bugs (omissions not marked, tool
  servers loaded again, default system prompt back, cached tokens left out of
  the count, markdown bold kept): each caught
- Real measurements of `claude -p` for the request "Reply with the single word
  OK." (2026-11-14, Claude Code 2.1.323, this machine's configuration):

  | how it was called | input tokens | model |
  |---|---|---|
  | as the backend did until today (`--tools ""` only) | 186 212 | the account default (Fable 5.2) |
  | same, with `--model haiku` | 185 566 | Haiku |
  | with the lean flags | 1 272 | Haiku |
  | through the fixed `ClaudeCodeBackend` | 1 236 | Haiku |

  The overhead depends on what the user has connected to Claude Code (many
  tool servers here), so the 186 000 is this machine's number, not a constant
- Review experiment. Input: the docstrings recorded on 2026-11-13 for the five
  samples, rebuilt through the current rules by replaying the recorded replies
  (30 docstrings per model; every prompt matched the recording). I read all 60
  and wrote an answer key **before** running the reviewer: 7B, 7 clearly false
  and 2 questionable; 1.5B, 12 clearly false and 4 questionable

  | Clio model | reviewer | requests | findings | clear falses caught | input / output tokens |
  |---|---|---|---|---|---|
  | 7B | Sonnet | 3 | 11 | 7 of 7 | 14 306 / 1 660 |
  | 7B | Haiku | 3 | 10 | 7 of 7 | 14 343 / 5 045 |
  | 1.5B | Sonnet | 3 | 23 | 12 of 12 | 19 450 / 1 962 |
  | 1.5B | Haiku | 3 | 19 | 12 of 12 | 19 485 / 8 939 |
  | 7B, after the fixes below | Sonnet | 3 | 9 | 7 of 7 | 14 629 / 1 504 |
  | 1.5B, after the fixes below | Sonnet | 3 | 21 | 12 of 12 | 19 597 / 1 903 |

- Most findings outside my key were real problems I had marked too kindly (for
  example `wrap` promising lines within the width when a long word exceeds it).
  Two of Sonnet's findings on the 1.5B output were muddled sentences that
  argued with themselves (`moving_average`, `truncate`); I did not count them
  as correct
- Limits of this result: one run per row; the answer key is mine and covers
  falsehood only, not redundancy; five small files I wrote myself; the reviewer
  was not tested on docstrings that are subtly wrong in larger code. It shows
  the stage works on real output, not how accurate it is
- Not run: the reviewer with the account's default model; the `anthropic`
  backend against the real API; anything on the 16B or 30B; Python other than
  3.12.3

**Problems found by running it for real**
- **Token overhead (mine).** I built and "verified" the Claude Code backend on
  2026-11-12 without measuring what a call cost, and wrote in the worklog that
  the token usage was not measured. It was about 186 000 input tokens per
  request, which defeats the purpose of the project. Found only when I asked
  the CLI for usage numbers. Fixed and now measured on every call
- **A wrong finding caused by my code.** Sonnet reported that the `Inventory`
  docstring "describes a `low_stock` method that does not exist in the code
  shown". The method exists; the critic showed only the top of the class and did
  not say so. Fixed: omitted lines are announced and the cut methods'
  signatures are listed. In the second run that finding was gone
- **A mistake while fixing it.** A one-off edit script opened
  `prompts/critic.txt` for writing before reading it and emptied the file. Two
  tests failed at once, I restored the file from `HEAD` (it had no other
  change), and re-applied the edit with the read-then-write helper

**Decisions**
- Lean flags are always on, not configurable — assistant's choice: a text-only
  review has no use for tools, skills or the agent's system prompt
- `prompt_tokens` counts cache writes and reads as input, because leaving them
  out is exactly how the 186 000 went unnoticed
- For a class cut short, list method signatures and not bodies: enough to check
  a docstring about what the class offers, at one line per method
- The experiment used Sonnet and Haiku, chosen by the assistant to see whether
  a cheaper reviewer is enough. `[review] model` in `momus.toml` is still empty,
  which means the account's default model (the most expensive one here). Which
  model to put there is the maintainer's decision

**Open / next**
- What Momus does with a finding: report only (today), remove the flagged
  docstring, or ask Clio again
- A default review model in `momus.toml`
- `momus bench` does not call the reviewer yet, so the "flagged by the
  reviewer" column of §11 is still empty
- Uncommitted: all of the above

## 2026-11-13 — Docstrings by default, comments on request (plan §2, §9)

**Changed**
- `src/momus/clio.py`: `DEFAULT_MODE = "docstrings"`, used by `comment_source()`
- `src/momus/cli.py`: `--mode` of `momus comment` and `momus bench` defaults to
  it; help text updated
- `tests/test_clio.py`, `tests/test_bench.py`: expectations updated, one test
  added (the default sends no comment request)
- `plan-Momus.md` §2 and §9, `CHANGELOG.md`

**Tests**
- Baseline before the change: 335 passed, 1 deselected
- After: `.venv/bin/pytest` — 336 passed, 1 deselected (integration)
- Real dry run: `.venv/bin/momus comment examples/retry.py` with the default
  model (`qwen2.5-coder:1.5b`) produced one docstring and no comment request;
  the file was unchanged afterwards (`git diff --quiet`)
- Not run: `--mode both` with a real model after this change (its code path
  did not change and is covered by the fake-backend tests)

**Decisions**
- Decided by the maintainer on the assistant's proposal: docstrings only by
  default. Reason and numbers are in the entry below; the inline-comment code
  stays, as an opt-in
- `momus bench` follows the same default, so a benchmark measures what the
  product does by default — assistant's choice; `--mode both` still measures
  the comments

**Open / next**
- Run the reviewer on Clio's output, where the false statements would be caught
- Uncommitted: the three doc files; the code is in the maintainer's commit
  `976254e`

## 2026-11-13 — Clio output quality, first pass (plan §9)

**Changed**
- `src/momus/quality.py` (new): `polish_docstring()`, `comment_problem()`,
  `copied_from_instructions()`, `is_placeholder()`
- `src/momus/clio.py`: docstrings pass through the polish and are wrapped to 79
  columns; comments are judged against the statement they sit above; at most
  `MAX_COMMENTS = 3` per function; text copied from the instructions is
  rejected; a method is shown inside a `class X:` header
- `src/momus/prompts/clio.txt`, `clio_comments.txt`: rewritten, no examples
- `src/momus/bench.py`: `power_source_at_end`
- `tests/test_quality.py` (new), more tests in `tests/test_clio.py`,
  `tests/test_bench.py`
- `plan-Momus.md` §9, `CHANGELOG.md`

**Tests**
- Baseline before this work: 258 passed, 1 deselected. After: `.venv/bin/pytest`
  — 335 passed, 1 deselected (integration). Fake backend only
- Mutation checks by hand in three batches (comment limit, section indent,
  wrapping; copy check in the rules and in Clio, methods list, bare
  instructions, paragraph joining): every deliberate bug was caught
- Three real rounds, `momus bench`, `qwen2.5-coder:1.5b` and `qwen2.5-coder:7b`
  on the five samples, mode `both`, 48 requests per model per round, no failed
  request, every insertion accepted by Argus in all rounds:

  | round | prompts and rules | 1.5B docstrings / comments in | 7B docstrings / comments in |
  |---|---|---|---|
  | 1 (2026-11-12) | first prompts, no rules | 30 / 29 | 30 / 2 |
  | 2 | prompts **with examples**, first rules | 30 / 24 (29 dropped) | 30 / 3 |
  | 3 | prompts without examples, more rules | 30 / 17 (52 dropped) | 30 / 1 (5 dropped) |
  | 3, replayed through the final rules | same replies, no new model call | 30 / 3 (66 dropped) | 30 / 1 (5 dropped) |

- The last row re-used the recorded replies of round 3 (the prompts had not
  changed), so it tests the rules, not the models
- No docstring line was over 79 columns in rounds 2 and 3. Round 1 had many,
  seen by reading; the count was not taken
- **Not benchmark data.** Round 1 ran on battery, round 2 started on mains with
  the machine just rebooted (load 3 to 12), round 3 on battery then mains. The
  seconds and tok/s of these runs are not comparable and are not reported
- The raw files of round 1 are lost: they were in `/tmp`, which was cleared by a
  restart. Its counts above come from the run's printed summary. Rounds 2 and 3
  are in `~/.cache/momus-quality/` on the maintainer's machine, outside the repo
- Not run: the 16B and 30B; `examples/retry.py`; the reviewer on any of this
  output; Python versions other than 3.12.3

**A regression I caused, and its fix**
- Round 2's prompts had an example docstring and example comments. The 1.5B
  copied them into the code: "Sort first: the median needs ordered values."
  inside `Inventory.remove`, the example paragraph about retries inside
  `low_stock` and `names`, and the context sentence "This method belongs to the
  class Inventory." inside a docstring. False text, invisible to Argus because
  the code was unchanged. Found by reading the diffs, not by a count
- Fix: no examples in the prompts; a method's class is shown as code, not said
  in a sentence; and `copied_from_instructions()` rejects any sentence of four
  words or more that appears in the prompt before the code. In round 3 that
  rule fired on no docstring

**What is still wrong (read from the diffs)**
- Truth. The 1.5B invents errors (`TypeError` for non-numbers, "raises
  ValueError if there are no items") and the 7B does it sometimes (a
  `low_stock_limit` argument on `low_stock`, a `TypeError` in `__init__`). No
  rule here can know that; the reviewer of §10 can
- The 1.5B's docstrings are still long and open with "The `mean` function...";
  the 7B's are short and mostly start with a verb
- The 3 comments the 1.5B keeps are weak reasons, one of them wrong ("a single
  value cannot be averaged with itself")
- A docstring is still inserted below a comment that already sits under the
  `def` line

**Decisions**
- Rules are heuristics that prefer dropping a good comment to keeping a bad one
  — assistant's choice, in line with "Momus would rather add nothing than add
  noise". The patterns are English-only
- Stopped adding patterns after the "narrating verb" rule: each new one caught
  less, and what remains needs judgement, not pattern matching
- The rules run before the comment limit, so a dropped comment does not use up
  one of the 3 places
- Docstring text is only re-spaced, re-wrapped and pruned of empty or
  code-duplicating sections; no word is rewritten
- Model choice is not decided here. On these files the 7B's text is clearly
  better and the 1.5B's inline comments are almost all noise, but that is two
  models on five files, and the comparison of all four is deferred

**Open / next**
- Whether inline comments should be on by default, given how few survive
- Running the reviewer on Clio's output, which is where the false statements
  would be caught
- Uncommitted: everything since the maintainer's last commit

## 2026-11-12 — Review stage, `momus review` (plan §10)

**Changed**
- `src/momus/critic.py` (new): `find_comments()`, `build_groups()`,
  `build_batches()`, `parse_findings()`, `review_changes()`,
  `read_git_baseline()`
- `src/momus/prompts/critic.txt` (new)
- `src/momus/backends/claude_code.py` and `anthropic.py` (new)
- `src/momus/config.py`: `[review]` table (`ReviewSettings`, loader, builder);
  the table reading is shared with `[local]`
- `src/momus/cli.py`: `momus review`; `momus.toml`: `[review]` section
- `tests/test_critic.py` (new, 55 tests); `tests/test_smoke.py`
- `plan-Momus.md` §10, §11, §15; `CHANGELOG.md`

**Tests**
- Baseline before changes: 204 passed, 1 deselected
- After: `.venv/bin/pytest` — 258 passed, 1 deselected (integration). Fake
  backend, fake process runner and a localhost stub server only
- Mutation check by hand, five deliberate bugs: the first attempt to skip the
  Argus checks was **not** caught (the earlier checks refused the same cases),
  so I added a test where only they can help (a `#` line added inside a
  multi-line string, which looks like a comment but changes the string). After
  that, all five were caught: Argus checks skipped, code left out of the
  request, finding at the wrong line, and Claude Code started with tools on
- Two test failures along the way: a wrong expectation about an error message,
  and `urllib` capitalizing header names. The first led to making the refusal
  message consistent
- Real run, once: a temporary git repository, a file with a false docstring
  ("median" on a mean), a redundant comment and a good comment, reviewed with
  `momus review` and `claude -p`. It printed `stats.py:2: The docstring says
  median, but the function returns the mean.` and `stats.py:3: Redundant; ...`,
  left the good comment alone, took about 10 s, and the file was not touched
- Not run: the `anthropic` backend against the real API (no call was made);
  the reviewer on real Clio output; token counts of the real call (not
  measured); Python versions other than 3.12.3

**Decisions**
- First real backend: Claude Code — assistant's choice, open to change: no key
  and no dependency, and the plan left it open (§13)
- Anthropic over plain HTTP, not the SDK — assistant's choice that departs from
  the plan's wording; consistent with the local backend and adds no dependency
- Review compares the working file with git (`--base`, default `HEAD`) instead
  of tracking what Momus wrote, because the ownership record (§16.7) does not
  exist yet. Consequence: any comment added since the baseline is reviewed,
  whoever wrote it, and an untracked or new file cannot be reviewed
- A change that edits or removes a line, or touches code, is refused as a
  whole file (fail closed). Trailing `# comments` on an existing line count as
  an edited line, so they are refused too
- The reviewer answers with comment numbers, not line numbers, and Momus maps
  them back — a small model-independent safeguard against wrong line numbers
- `claude -p` runs with all tools off, no saved session, from an empty folder
  so this project's instructions are not loaded each time. User-level
  instructions and hooks may still load; not checked
- Exit status: 0 when every file was reviewed (findings or not), 1 when a file
  or request could not be — assistant's choice; findings alone do not fail
- The benchmark and the four-model comparison are deferred to the end, by the
  maintainer; `momus bench` does not call the reviewer yet

**Open / next**
- The next plan step by the order of §15 is §12 (README, logo, publication),
  but §9 still has the output-quality work and §16 (settings app, daemon) is
  large; the maintainer chooses
- Uncommitted: all of the above

## 2026-11-12 — Benchmark engine, `momus bench` (plan §11)

**Changed**
- `src/momus/bench.py` (new): `RecordingBackend`, `OllamaInfo`,
  `collect_machine_conditions()`, `run_model()`, `summarize()`, `write_run()`,
  `run_comparison()`, `main()`
- `src/momus/cli.py`: `momus bench` (`--models`, `--files`, `--mode`, `--out`,
  `--config`, `--notes`, `--keep-loaded`)
- `src/momus/clio.py`: `Outcome` gained `kind` and `cause`
- `src/momus/backends/local.py`: `last_usage` (token counts from the server)
- `tests/test_bench.py` (new, 14 tests); one test each added to
  `tests/test_clio.py` and two to `tests/test_backends.py`; `tests/test_smoke.py`
  no longer treats `bench` as a placeholder
- `plan-Momus.md` §11 (status note) and §17 (app feature idea), `CHANGELOG.md`

**Tests**
- Baseline before changes: 188 passed, 1 deselected
- After: `.venv/bin/pytest` — 204 passed, 1 deselected (integration). No model
  and no Ollama in the suite
- Two of my own tests found a real bug before any run: result files were named
  `..._qwen2.json` for `qwen2.5-coder:*` because `Path.with_suffix` took
  `.5-coder-7b` for an extension, so two Qwen models could have overwritten
  each other's results. Fixed by appending the extension as text. A third test
  failure was a wrong expectation in the test itself
- Mutation check by hand, three deliberate bugs (wrong guard-acceptance
  formula, unloading when told not to, ignoring the installed-model check): each
  caught
- Real script check: `momus bench --models qwen2.5-coder:1.5b ghost-model:1b
  --files benchmarks/samples/stats.py`, output in a throwaway folder. It wrote
  both files for each model, recorded the conditions, and marked the missing
  model "not installed" without calling it. The samples were untouched
- That check ran on **battery** (`AC online = 0`, "Discharging"), the plan
  requires mains, so its numbers (for the record: 16 insertions accepted, 10
  requests, 50.8 s, 16.0 tok/s) are **not benchmark data** and were deleted
- Not run: any official comparison, the 7B, 16B and 30B through `momus bench`,
  Python versions other than 3.12.3

**Decisions**
- Wired as the planned `momus bench` command instead of a loose script, so the
  same engine can serve the final app, as the maintainer asked. Assistant's
  choice of shape: a plain module with no argument parsing in it
- Dry run only: the engine reads the sample files and never writes them
- One JSON (everything raw: each prompt, reply, seconds and token count) and
  one Markdown (conditions, summary, per-file table, diffs to review) per model
  per run
- Models are unloaded before each run (`--keep-loaded` turns that off), so each
  first request is a true cold load and models do not share memory. This does
  unload models the maintainer may have loaded
- Conditions recorded: power source (from `/sys`), power profile and CPU
  governor, load average and free memory at the start, Ollama version, model
  details and quantization, context length seen, commit (with a note if there
  are uncommitted changes), and free-text `--notes`. Process names are not
  recorded, since the files are meant to be published
- Speed is completion tokens over wall-clock seconds, so it includes prompt
  reading; the first request is reported separately because it may include the
  model load. Context length is left at the server's default (4096 here) for
  every model, for consistency
- The plan's main metric, accepted insertions per minute of model time, and the
  Argus acceptance share are in the summary. "Trivial or wrong comments" is for
  a person to judge from the diffs; "flagged by the reviewer" waits for §10

**Open / next**
- The official run: plug in, close heavy applications, then the four models.
  Plan: the assistant runs `qwen2.5-coder:1.5b` and `7b`, the maintainer runs
  `deepseek-coder-v2:16b` and `qwen3-coder:30b`
- Uncommitted: all of the above

## 2026-11-12 — Clio, slice 2: inline comments (plan §9)

**Changed**
- `src/momus/clio.py`: `parse_comments()`, `format_comment()`,
  `build_comment_prompt()`, statement numbering (`_statements`, `_comment_slot`,
  `_numbered`), comment insertion in `comment_source(..., mode=)`; the reply
  reading shared with the docstring slice moved into `_after_marker()`
- `src/momus/prompts/clio_comments.txt` (new)
- `src/momus/cli.py`: `--mode {both,docstrings,comments}`
- `tests/test_clio.py`: 24 more tests (55 in the file); the slice-1 tests now
  ask for `mode="docstrings"` explicitly
- `plan-Momus.md` §9, `CHANGELOG.md`

**Tests**
- Baseline before changes: 164 passed, 1 deselected
- After: `.venv/bin/pytest` — 188 passed, 1 deselected (integration). Fake
  backend only
- Mutation check by hand, four deliberate bugs (comment one line too low,
  existing comments ignored, unknown statement numbers accepted, docstring and
  comment in the wrong order at the same line): each was caught
- Two of my first test runs failed because of mistakes in the tests (a column
  offset, and a status dict that merged two outcomes); the code was right
- Real runs, dry-run: `retry.py` with `qwen2.5-coder:1.5b` and `7b`, both
  `COMMENTS: NONE`. `stats.py`: the 1.5B added 11 comments across 5 functions
  (4 in one function, the prompt says at most 3), the 7B proposed none
- Real `--write` on a temporary copy of `report_lines.py` with the 1.5B, mode
  `both`: 24 lines inserted. Checked independently of Clio (`difflib` for the
  inserted lines, then both Argus checks): no line edited, code identical, mode
  0640 kept, no temp file left, all four hand-written texts intact
- Not run: the 16B and 30B models; the remaining samples; Python versions other
  than 3.12.3. No timings, no recorded conditions: **not benchmark data**

**What the real runs showed (one run each, first impressions)**
- 1.5B: follows the format and names valid statements every time it was seen,
  but the comments restate the code ("This checks if the input list is
  empty"), and some sit on the wrong statement (a comment about the loop above
  `return None`). Its docstrings are long and describe the code line by line
- 7B: proposes nothing for the small functions it was given. That obeys
  "fewer is better", but whether it ever comments is not known yet
- A docstring is inserted directly above the first statement, so it ends up
  below a person's comment that already sits there (`worst_severity`). Valid
  Python, odd to read

**Decisions**
- Docstrings and comments are separate requests, not one combined reply —
  assistant's choice: a simpler format is easier for a small model, and each
  can be switched off with `--mode`
- Comments only for functions and methods, not classes
- A function with fewer than 3 numbered statements is not offered
  (`MIN_STATEMENTS = 3`) — assistant's choice, to be revisited with real files
- Numbered statements include those in nested blocks, `try` handlers and
  `match` cases; nested functions and classes count as one statement and are
  not entered
- A statement is never offered if it has a comment above it or on its line: a
  person's comment is not Momus's to join or replace (§16.7, ownership). This
  is the full rule for now, since there is no record of what Momus wrote
- Comment lines are wrapped at about 79 columns and inserted as separate `#`
  lines
- A reply line not in the `S3: text` format is ignored, unless there is no valid
  line at all, in which case the reply is rejected
- The "at most 3 comments" limit lives only in the prompt; the code does not
  enforce it (the 1.5B went over it)
- Fingerprints, occurrence numbers and re-finding Momus's comments are not
  built; the statement numbers are valid only within one run

**Open / next**
- The four-model comparison on the five sample files, with the prompt as it is
- Then prompt tuning, using results from all models instead of one function
- Uncommitted: all of the above

## 2026-11-12 — Clio, slice 1: docstrings only (plan §9)

**Changed**
- `src/momus/clio.py` (new): `comment_source()`, `parse_reply()`,
  `format_docstring()`, `build_prompt()`, `read_text_exact()`,
  `write_text_atomic()`, `Outcome`, `ClioResult`
- `src/momus/prompts/clio.txt` (new) and `pyproject.toml` (`package-data` so the
  prompt ships with the package)
- `src/momus/cli.py`: `momus comment FILE... [--write] [--model] [--config]`
- `src/momus/cleaning.py`: `strip_reasoning()` split out of `clean_output()`
  (no behaviour change)
- `tests/test_clio.py` (31 tests); `tests/test_smoke.py`: `comment` is no
  longer in the list of placeholder commands
- `plan-Momus.md` §9, `CHANGELOG.md`

**Tests**
- Baseline before changes: 134 passed, 1 deselected
- After: `.venv/bin/pytest` — 164 passed, 1 deselected (integration). The fake
  backend only; no test calls a model
- Mutation check by hand (code broken on purpose, then restored): guard always
  passing, replacing existing docstrings, and inserting after decorators were
  each caught by a test
- Real runs, dry-run, `examples/retry.py`, `.venv/bin/momus comment`: both
  `qwen2.5-coder:1.5b` and `qwen2.5-coder:7b` produced a diff with exactly one
  inserted docstring; the file was byte-identical afterwards (`cmp`).
  Conditions not recorded, no timings taken: **not benchmark data**
- Not run: `--write` with a real model; the other five sample files; any
  Python other than 3.12.3; the 16B and 30B models

**Bug found by the real run, fixed**
- First run: the 1.5B was rejected ("reply does not start with DOCSTRING:").
  Its raw reply did start with the marker, then repeated the code in a fence.
  `clean_output()` keeps the first fenced block, so it kept the echoed code
  and lost the docstring. Safe (nothing written) but it threw away a usable
  answer. `parse_reply()` now reads the marker first and ends the text at a
  "Code:" label or a fence. Two tests cover it

**Quality of what the models wrote (observation, one function each)**
- 1.5B: one very long line that restates the code, as in "The `retry` function
  is a utility that..."
- 7B: a better summary, but a first line over 100 characters, "Args:" entries
  without indentation, and "Raises: last_error", which names the variable, not
  an exception type
- The prompt is the first version and has not been tuned. Judging quality is
  the job of the four-model comparison, not of this entry

**Decisions**
- Order agreed with the maintainer: docstrings first, inline comments (slice 2)
  after, then the comparison
- Targets: top-level functions and classes, and the methods directly inside a
  class. Nested functions and module docstrings are not covered yet
- The docstring goes right before the first statement of the body, after any
  comment lines already there, and above a decorator if the first statement is
  a decorated method
- A target whose body shares the `def` line is skipped, and so is any target
  that already has a docstring, which also means the model is not called for it
  (ownership, §16.7). Slice 1 has no record of what Momus wrote, so it cannot
  rewrite its own docstrings either
- Each insertion is checked alone, and the combined result is checked again.
  If the combined check ever failed, nothing is kept
- A reply containing a triple double quote is rejected; backslashes are
  doubled. Quotes around the text are removed
- `--write` goes through a temporary file in the same folder and `os.replace`,
  keeps the permissions, and reads and writes with `newline=""` so line endings
  are preserved. A file that is not valid UTF-8 is reported and left alone
- `--model` overrides the model in `momus.toml` for one run, so the comparison
  needs no config edits — assistant's choice

**Open / next**
- Slice 2: inline `#` comments with statement numbers; the plan marks that
  reply format as untested
- The four-model comparison on the five sample files, then the output-quality
  questions above
- A cap on reply length (`max_tokens`) is available in `momus.toml` but not
  set; on this CPU a rambling reply costs time
- Uncommitted: everything from the sample files onwards

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
