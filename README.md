# Momus

![Momus logo: a Greek theatrical mask with a magnifying lens over one eye](assets/social-preview.png)

*A cheap code-commenting pipeline that does not trust its own comments.*

---

Momus is a small Python pipeline that documents freshly written code while spending very few tokens. A **local language model** does the repetitive work. A **stronger model** only does the final check.

It is named after Momus, the Greek god of criticism, because the project does not trust generated comments: it verifies them.

> **Status: work in progress.** The three stages run from the command line and are covered by tests. What is still missing is measurement: there is no benchmark table yet, and the reviewer has only been tried on a small sample (see [What has been measured](#what-has-been-measured)). The working plan is in [`plan-Momus.md`](plan-Momus.md), the history in [`CHANGELOG.md`](CHANGELOG.md) and [`WORKLOG.md`](WORKLOG.md).

## How it works

Three stages, named after figures from Greek mythology:

| Stage | Name | What it does | Model needed |
| ------- | ------ | -------------- | -------------- |
| 1 | **Clio** | Writes the missing docstrings (and, on request, inline comments) for the files you name or the ones changed since the last commit, one function, class or file at a time. | Local model |
| 2 | **Argus** | Compares the code before and after using Python's `ast` module, ignoring comments and docstrings, and checks that only whole lines were added. If anything else changed, the output is discarded. | None |
| 3 | **Momus** | Shows a stronger model each added comment next to the code it describes, and reports the ones that are false, redundant or inconsistent. | Strong model |

Clio, the muse of history, writes. Argus, the giant with a hundred eyes, watches. Momus, the god of criticism, finds fault.

The review output is deliberately short: **file, line, problem**.

```text
changed files  ->  Clio (local LLM)  ->  Argus (AST guard)  ->  Momus (strong LLM review)
                   writes docstrings     rejects any code       flags wrong or
                                         change                 redundant comments
```

The local model never writes code and never decides where anything goes. It returns only the text of a docstring; Momus finds the place and inserts the lines itself, and Argus checks every insertion.

## Example

Real output, not an illustration: `momus comment benchmarks/samples/async_tools.py --model qwen2.5-coder:7b`, run on 2026-11-16. The lines marked `+` are what the model added; everything else is the original file.

```diff
 @timed
 async def gather_limited(factories, limit=3):
+    """Gathers results from asynchronous factory functions with a concurrency
+    limit.
+
+    Awaits the completion of all factory functions, limiting concurrent
+    executions to a specified number. Raises an error if any factory function
+    raises one.
+
+    Args:
+        factories (list): A list of asynchronous factory functions.
+        limit (int): The maximum number of concurrent executions.
+
+    Returns:
+        list: A list of results from the factory functions.
+    """
     semaphore = asyncio.Semaphore(limit)

     async def run(factory):
+        """Runs a factory coroutine within a semaphore limit.
+
+        Acquires a semaphore slot before running the factory and releases it
+        afterward. This ensures that no more than `limit` factories are running
+        concurrently.
+        """
         async with semaphore:
             return await factory()
```

The same run also produced a weaker docstring, for a small wrapper function, with a paragraph that begins "Caller must know:", words lifted from Momus's own instructions. Output like that is why the third stage exists.

## Install

Momus needs Python 3.11 or newer and has no third-party runtime dependencies.

```bash
git clone https://github.com/MarcoPannocchia/Cybe-Dev-Momus.git
cd Cybe-Dev-Momus
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # installs the `momus` command
```

You also need:

- **A local model server** that speaks the OpenAI chat format. [Ollama](https://ollama.com) is what Momus is developed with; [llama.cpp](https://github.com/ggml-org/llama.cpp) and [LM Studio](https://lmstudio.ai) should work the same way but have not been tried. Pull a code model yourself, for example `ollama pull qwen2.5-coder:7b`, and set its name in `momus.toml`.
- **For the review stage only**, one of: the [Claude Code](https://claude.com/claude-code) command `claude`, logged in (no API key needed), or an Anthropic API key in the `ANTHROPIC_API_KEY` environment variable. The API route is built but has only been tested against a stand-in server, never the real API.

To run the tests: `pip install -r requirements-dev.txt`, then `pytest`. The tests use no model and no network.

## Usage

Settings live in [`momus.toml`](momus.toml), which is commented line by line: the local server's address and model, and the review backend and models. API keys never go in that file.

```bash
# 1. Clio: show the docstrings the local model would add. Nothing is written.
momus comment path/to/file.py

# With no file names: every .py file changed or created since the last commit.
momus comment

# Write them into the files (each insertion has passed Argus first).
momus comment path/to/file.py --write

# Inline comments are off by default; ask for them with --mode.
momus comment path/to/file.py --mode both

# 2. Argus: is this file still its committed version plus comments only?
momus guard path/to/file.py
momus guard path/to/file.py --code-only    # also accept edited or removed comments

# 3. Momus: have the strong model read the comments added since the last commit.
momus review path/to/file.py
momus review path/to/file.py --drop        # and remove the ones it flags

# Compare local models on the same files (results go to benchmarks/results/).
momus bench --models qwen2.5-coder:1.5b qwen2.5-coder:7b
momus bench --review                       # also count what the reviewer flags
```

`momus <command> --help` lists every option. `guard` and `review` compare a file with its version in git, so they need a file that has been committed at least once.

## Design choices

- **The code is never modified, only comments.** Argus enforces this with two checks: the syntax tree must be identical once comments and docstrings are set aside, and removing the added lines must give back the original text exactly. It does not depend on the model behaving well, and when in doubt it rejects.
- **Dry run by default.** `momus comment` only shows a diff unless you pass `--write`.
- **Existing comments are left alone.** Clio adds a docstring only where there is none.
- **Backends are interchangeable.** No stage is tied to a specific model or provider. The OpenAI format is used only as a local protocol; the review uses Claude through Claude Code or the Anthropic API.
- **Cheap review.** Short files go to a cheaper model and long ones to a stronger one (`small_model`, `small_file_lines` in `momus.toml`).
- **Python files only (`.py`)** in this first version.
- **Built for CPU-only machines.** The pipeline is a batch job (start it and do something else), not an interactive tool.

## Usage ledger

`momus comment` and `momus review` append one line per model request to `~/.local/state/momus/<project>/usage.jsonl` (or under `$XDG_STATE_HOME`): tokens in and out, seconds, and what came of the request. It holds numbers only, never code, comment text or file names, and it sits outside your project, so your repository is not touched.

## What has been measured

Nothing here is a benchmark yet. These are single runs on one laptop, recorded with their circumstances in [`WORKLOG.md`](WORKLOG.md):

- **Reviewer, first trial (2026-11-14).** 60 docstrings written by two local models for five small sample files were reviewed through Claude Code. Against an answer key written beforehand, the reviewer flagged every docstring marked as clearly false: 7 of 7 for the 7B model's output and 12 of 12 for the 1.5B's, with Sonnet and with Haiku alike. One run per row, an answer key written by the same AI assistant that built the stage, five small files: an encouraging first result, not an accuracy figure.
- **Cost of that review.** Reviewing 30 docstrings took 3 requests and about 14,600 input and 1,500 output tokens (7B output, Sonnet).
- **Speed.** On CPU, with `qwen2.5-coder:7b`, one file with eight targets took 2 minutes 40 seconds (one run, other programs open).

The comparison of local models (`momus bench`) is built but has not been run for the record.

## Known limits

- Local models on CPU are slow: this is not an interactive workflow.
- A local model can write a docstring that is wrong while the code stays intact. Argus cannot catch that; the review stage is there for it, and how often the reviewer itself misses one has not been measured.
- Every nested function, however small, gets a docstring.
- `momus review` looks at every comment added since the last commit, including ones you wrote yourself, and `--drop` removes whichever of them it flags. Momus does not yet keep a record of which comments are its own.
- A file that has never been committed can be commented but not reviewed or guarded.
- Only `.py` files are supported.
- Developed and tested on Linux with Python 3.12 only.

## Model weights

This repository does **not** include any model weights. Download the model you want to use from its original source and follow its license.

## Author

Marco Pannocchia
