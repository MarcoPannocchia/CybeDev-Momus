<p align="center">
  <img src="assets/logo.png" alt="Momus logo: a Greek theatrical mask with a magnifying lens over one eye" width="320">
</p>

<h1 align="center">Momus</h1>

<p align="center">
  <em>A cheap code-commenting pipeline that does not trust its own comments.</em>
</p>

---

Momus is a small Python pipeline that documents freshly written code while spending very few tokens. A **local language model** does the repetitive work. A **stronger model** only does the final check.

It is named after Momus, the Greek god of criticism, because the project does not trust generated comments: it verifies them.

> **Status: early work in progress.** The design below is settled, but the code is being built step by step. Benchmarks and before/after examples will be added as each part works, including the cases where it fails.

## How it works

Three stages, named after figures from Greek mythology:

| Stage | Name | What it does | Model needed |
|-------|------|--------------|--------------|
| 1 | **Clio** | Adds comments and docstrings to the files changed in your `git diff`, one file or function at a time. | Local model |
| 2 | **Argus** | Compares the code before and after using Python's `ast` module, ignoring comments and docstrings. If the code changed in any way, the output is discarded. | None |
| 3 | **Momus** | Builds a compact diff of the comments only and sends it to a stronger model, which flags comments that are false, redundant or inconsistent across modules. | Strong model |

The review output is deliberately short: **file, line, problem**.

```
git diff  ->  Clio (local LLM)  ->  Argus (AST guard)  ->  Momus (strong LLM review)
              writes comments       rejects any code      flags wrong or
                                    change                redundant comments
```

## Planned CLI

```bash
momus comment   # Clio: generate comments for the changed files
momus guard     # Argus: reject any output that changes the code
momus review    # Momus: final review of the comments with a stronger model
```

## Design choices

- **The code is never modified, only comments.** Argus enforces this with an AST comparison, so it does not depend on the model behaving well.
- **Comments explain *why*, not *what*.**
- **Backends are interchangeable.** No stage is tied to a specific model or provider.
  - The local model is served through any OpenAI-compatible API ([Ollama](https://ollama.com), [llama.cpp](https://github.com/ggml-org/llama.cpp), [LM Studio](https://lmstudio.ai)). The OpenAI format is used only as a local protocol.
  - The final review uses Claude, through the Anthropic API or Claude Code from the terminal.
- **Python files only (`.py`)** in this first version.
- **Built for CPU-only machines.** The pipeline is designed as a batch job (start it and do something else), not as an interactive tool.

## Known limits (so far)

- Local models running on CPU are slow, so this is not an interactive workflow.
- A small local model can write comments that are wrong while the code stays intact. Argus cannot catch that, which is exactly why the review stage exists.
- Only `.py` files are supported.

More limits and observed failures will be listed here as they are measured.

## Model weights

This repository does **not** include any model weights. Download the model you want to use from its original source and follow its license.

## Roadmap

- [ ] Local runtime installed and model responding
- [ ] Script that calls the local model through the OpenAI-compatible API
- [ ] `clio`: comment a single file
- [ ] `argus`: AST guard with tests
- [ ] `review`: compact comment diff for the strong model
- [ ] Before/after examples
- [ ] Small benchmark: tokens saved, outputs discarded, comments judged correct

## Author

Marco Pannocchia

[![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/marco-pannocchia-191924433/)
[![Instagram](https://img.shields.io/badge/Instagram-E4405F?style=for-the-badge&logo=instagram&logoColor=white)](https://www.instagram.com/marco_pannocchia/)
