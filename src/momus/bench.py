"""Benchmark: run Clio with several models over the same files and record how it went.

This is the engine behind ``momus bench``. It never writes to the files it
reads: Clio runs as a dry run, and the only files written are the result files.

For every model it saves one JSON file with everything raw (each prompt, each
reply, seconds and token counts per request, every outcome, the generated
diff) and one Markdown file with the summary and the diffs for a person to
read. Both start with the measurement conditions, so a number can be judged
against the circumstances it was taken in.

Numbers here are measurements of one run on one machine. The speed figures are
wall-clock: they include the time the model spends reading the prompt and,
for the first request, loading the model.
"""

import difflib
import glob
import json
import os
import platform
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from momus.backends import Backend, BackendError
from momus.clio import ADDED, REJECTED, SKIPPED, ClioError, comment_source, read_text_exact
from momus.config import LocalSettings, build_local_backend, load_local_settings

DEFAULT_MODELS = (
    "qwen2.5-coder:1.5b",
    "qwen2.5-coder:7b",
    "deepseek-coder-v2:16b",
    "qwen3-coder:30b",
)
DEFAULT_SAMPLES = "benchmarks/samples/*.py"
DEFAULT_OUT = "benchmarks/results"


# --- Recording what the model is asked and answers ---------------------------


@dataclass
class Request:
    """One call to the model."""

    prompt: str
    reply: str | None
    seconds: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None


class RecordingBackend:
    """Wraps a backend and keeps every request, for the result file."""

    def __init__(self, inner: Backend) -> None:
        self.inner = inner
        self.requests: list[Request] = []

    def complete(self, prompt: str) -> str:
        started = time.perf_counter()
        try:
            reply = self.inner.complete(prompt)
        except BackendError as exc:
            self.requests.append(Request(prompt, None, time.perf_counter() - started, error=str(exc)))
            raise
        usage = getattr(self.inner, "last_usage", None) or {}
        self.requests.append(
            Request(
                prompt,
                reply,
                time.perf_counter() - started,
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
            )
        )
        return reply


# --- Talking to Ollama (optional: everything here may fail quietly) ----------


class OllamaInfo:
    """Read-only questions to an Ollama server, plus unloading models.

    Every method returns ``None`` (or an empty list) when the server is not
    Ollama or does not answer, so the benchmark still runs against any
    OpenAI-format server, just with fewer conditions recorded.
    """

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self.root = re.sub(r"/v1/?$", "", base_url.rstrip("/"))
        self.timeout = timeout

    def _call(self, path: str, payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.root + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except (OSError, ValueError):
            return None

    def version(self) -> str | None:
        data = self._call("/api/version")
        return data.get("version") if isinstance(data, dict) else None

    def installed(self) -> list[str] | None:
        data = self._call("/api/tags")
        if not isinstance(data, dict):
            return None
        return [m.get("name", "") for m in data.get("models", [])]

    def loaded(self) -> list[dict]:
        data = self._call("/api/ps")
        return list(data.get("models", [])) if isinstance(data, dict) else []

    def details(self, model: str) -> dict | None:
        data = self._call("/api/show", {"model": model})
        return data.get("details") if isinstance(data, dict) else None

    def unload_all(self) -> list[str]:
        """Unload every loaded model, so the next first request is a cold load."""
        names = [m.get("name", "") for m in self.loaded()]
        for name in names:
            self._call("/api/generate", {"model": name, "keep_alive": 0})
        return names


# --- Measurement conditions --------------------------------------------------


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _power_source() -> str:
    """Say whether the machine is on mains or battery, from the kernel's own files."""
    mains, battery = None, None
    for folder in sorted(glob.glob("/sys/class/power_supply/*")):
        kind = _read(f"{folder}/type")
        if kind == "Mains" and _read(f"{folder}/online") == "1":
            mains = True
        elif kind == "Mains" and mains is None:
            mains = False
        elif kind == "Battery":
            battery = _read(f"{folder}/status")
    if mains is None and battery is None:
        return "unknown (no power information found)"
    if mains:
        return f"mains (battery: {battery or 'none'})"
    return f"battery (status: {battery or 'unknown'})"


def _command(args: list[str]) -> str | None:
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def _meminfo_gb(field_name: str) -> float | None:
    text = _read("/proc/meminfo") or ""
    match = re.search(rf"^{field_name}:\s+(\d+) kB", text, re.MULTILINE)
    return round(int(match.group(1)) / 1024 / 1024, 1) if match else None


def collect_machine_conditions(notes: str = "") -> dict:
    """Describe the machine and how busy it is. Never raises.

    Process names are deliberately not recorded: the result files are meant to
    be published. Load and free memory are the evidence that other heavy
    applications were closed; ``notes`` is for the operator to say so too.
    """
    cpu = None
    for line in (_read("/proc/cpuinfo") or "").splitlines():
        if line.startswith("model name"):
            cpu = line.split(":", 1)[1].strip()
            break
    try:
        load = round(os.getloadavg()[0], 2)
    except OSError:
        load = None
    commit = _command(["git", "rev-parse", "--short", "HEAD"])
    dirty = _command(["git", "status", "--porcelain"])
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "os": platform.platform(),
        "cpu": cpu,
        "cpu_threads": os.cpu_count(),
        "ram_total_gb": _meminfo_gb("MemTotal"),
        "ram_available_gb_at_start": _meminfo_gb("MemAvailable"),
        "load_average_1m_at_start": load,
        "power_source": _power_source(),
        "power_profile": _command(["powerprofilesctl", "get"]) or "unknown (not detected)",
        "cpu_governor": _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
        or "unknown",
        "python": platform.python_version(),
        "momus_commit": (commit or "unknown") + (" (uncommitted changes)" if dirty else ""),
        "operator_notes": notes,
    }


# --- Running one model -------------------------------------------------------


@dataclass
class FileRun:
    path: str
    seconds: float
    outcomes: list[dict]
    diff: str
    error: str | None = None


@dataclass
class ModelRun:
    model: str
    conditions: dict
    mode: str
    files: list[FileRun] = field(default_factory=list)
    requests: list[Request] = field(default_factory=list)
    skipped_reason: str | None = None


def run_model(
    model: str,
    backend: Backend,
    paths: list[Path],
    mode: str,
    conditions: dict,
) -> ModelRun:
    """Run Clio over ``paths`` with ``backend``, as a dry run, and record everything."""
    run = ModelRun(model, conditions, mode)
    recorder = RecordingBackend(backend)
    for path in paths:
        started = time.perf_counter()
        try:
            source = read_text_exact(path)
        except (OSError, ClioError) as exc:
            run.files.append(FileRun(str(path), 0.0, [], "", f"cannot read: {exc}"))
            continue
        result = comment_source(source, recorder, mode)
        diff = "".join(
            difflib.unified_diff(
                source.splitlines(keepends=True),
                result.text.splitlines(keepends=True),
                fromfile=f"a/{path.name}",
                tofile=f"b/{path.name}",
            )
        )
        outcomes = [vars(outcome).copy() for outcome in result.outcomes]
        run.files.append(FileRun(str(path), time.perf_counter() - started, outcomes, diff))
    run.requests = recorder.requests
    return run


def summarize(run: ModelRun) -> dict:
    """Turn a run into the numbers of the plan's table.

    ``accepted_per_minute`` is the plan's main metric: insertions that passed
    Argus, divided by the time spent in the model. ``tokens_per_second`` is
    completion tokens over wall-clock seconds, so it includes prompt reading.
    """
    outcomes = [o for f in run.files for o in f.outcomes]
    by = Counter((o["kind"], o["status"]) for o in outcomes)
    causes = Counter(o["cause"] for o in outcomes if o["status"] == REJECTED)
    added = by[("docstring", ADDED)] + by[("comment", ADDED)]
    guard_rejected = causes["guard"]
    request_seconds = sum(r.seconds for r in run.requests)
    completion = [r.completion_tokens for r in run.requests if r.completion_tokens is not None]
    prompt = [r.prompt_tokens for r in run.requests if r.prompt_tokens is not None]
    token_seconds = sum(r.seconds for r in run.requests if r.completion_tokens is not None)
    return {
        "files": len(run.files),
        "files_unreadable": sum(1 for f in run.files if f.error),
        "requests": len(run.requests),
        "requests_failed": sum(1 for r in run.requests if r.error),
        "seconds_total": round(sum(f.seconds for f in run.files), 1),
        "seconds_per_file": round(sum(f.seconds for f in run.files) / len(run.files), 1)
        if run.files
        else None,
        "first_request_seconds": round(run.requests[0].seconds, 1) if run.requests else None,
        "prompt_tokens": sum(prompt) if prompt else None,
        "completion_tokens": sum(completion) if completion else None,
        "tokens_per_second": round(sum(completion) / token_seconds, 1)
        if completion and token_seconds
        else None,
        "docstrings_added": by[("docstring", ADDED)],
        "docstrings_rejected": by[("docstring", REJECTED)],
        "docstrings_skipped": by[("docstring", SKIPPED)],
        "comments_added": by[("comment", ADDED)],
        "comments_rejected": by[("comment", REJECTED)],
        "comments_skipped": by[("comment", SKIPPED)],
        "rejected_by_cause": dict(causes),
        "accepted_total": added,
        "guard_acceptance": round(added / (added + guard_rejected), 3)
        if added + guard_rejected
        else None,
        "accepted_per_minute": round(added / (request_seconds / 60), 2)
        if request_seconds
        else None,
        "request_seconds": round(request_seconds, 1),
    }


# --- Writing results ---------------------------------------------------------


def _slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]+", "-", model).strip("-")


def render_markdown(run: ModelRun, summary: dict) -> str:
    """Human-readable summary of a run, ending with the diffs to review."""
    lines = [f"# Benchmark: {run.model}", ""]
    if run.skipped_reason:
        return "\n".join([*lines, f"**Not run:** {run.skipped_reason}", ""])
    lines += ["## Conditions", ""]
    lines += [f"- {key}: {value}" for key, value in run.conditions.items()]
    lines += ["", "## Summary", "", "| metric | value |", "|---|---|"]
    lines += [f"| {key} | {value} |" for key, value in summary.items()]
    lines += [
        "",
        "Speed figures are wall-clock and include prompt reading; "
        "`first_request_seconds` includes loading the model if it was cold.",
        "",
        "## Per file",
        "",
        "| file | seconds | added | rejected | skipped |",
        "|---|---|---|---|---|",
    ]
    for f in run.files:
        count = Counter(o["status"] for o in f.outcomes)
        note = f" ({f.error})" if f.error else ""
        lines.append(
            f"| {Path(f.path).name}{note} | {f.seconds:.1f} | "
            f"{count[ADDED]} | {count[REJECTED]} | {count[SKIPPED]} |"
        )
    lines += ["", "## Generated text, for review", ""]
    for f in run.files:
        lines += [f"### {Path(f.path).name}", "", "```diff", f.diff.rstrip() or "(no change)", "```", ""]
    return "\n".join(lines)


def write_run(run: ModelRun, out_dir: Path) -> tuple[Path, Path]:
    """Write the JSON (raw) and Markdown (readable) files of one run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = out_dir / f"{stamp}_{_slug(run.model)}"
    summary = None if run.skipped_reason else summarize(run)
    payload = {
        "model": run.model,
        "mode": run.mode,
        "conditions": run.conditions,
        "skipped_reason": run.skipped_reason,
        "summary": summary,
        "files": [vars(f) for f in run.files],
        "requests": [vars(r) for r in run.requests],
    }
    # Appended as text: model names contain dots, and `with_suffix` would take
    # ".5-coder-7b" for an extension and replace it.
    json_path, md_path = Path(f"{stem}.json"), Path(f"{stem}.md")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(run, summary or {}), encoding="utf-8")
    return json_path, md_path


# --- The command -------------------------------------------------------------


def run_comparison(
    models: list[str],
    paths: list[Path],
    settings: LocalSettings,
    mode: str,
    out_dir: Path,
    notes: str = "",
    unload: bool = True,
    ollama: OllamaInfo | None = None,
    make_backend=build_local_backend,
    log=print,
) -> list[ModelRun]:
    """Run every model over every file and write one result pair per model.

    With ``unload`` (the default) all loaded models are unloaded before each
    model, so its first request is a true cold load and models do not share
    memory. A model that is not installed is recorded as not run instead of
    failing request by request.
    """
    ollama = ollama or OllamaInfo(settings.base_url)
    installed = ollama.installed()
    runs = []
    for model in models:
        log(f"== {model}")
        conditions = collect_machine_conditions(notes)
        conditions["ollama_version"] = ollama.version() or "unknown (not Ollama, or not answering)"
        conditions["model_details"] = ollama.details(model) or "unknown"
        if installed is not None and model not in installed:
            run = ModelRun(model, conditions, mode, skipped_reason="not installed (see `ollama list`)")
        else:
            if unload:
                conditions["unloaded_before_run"] = ollama.unload_all()
            run = run_model(model, make_backend(replace(settings, model=model)), paths, mode, conditions)
            loaded = [m for m in ollama.loaded() if m.get("name") == model]
            conditions["context_length_seen"] = (loaded[0].get("context_length") if loaded else None) or "unknown"
        json_path, md_path = write_run(run, out_dir)
        log(f"   wrote {json_path} and {md_path}")
        if not run.skipped_reason:
            stats = summarize(run)
            log(
                f"   {stats['accepted_total']} accepted, {stats['requests']} requests, "
                f"{stats['seconds_total']} s, {stats['tokens_per_second']} tok/s"
            )
        runs.append(run)
    return runs


def main(args) -> int:
    """Entry point for ``momus bench``; ``args`` comes from the CLI parser."""
    try:
        settings = load_local_settings(args.config)
    except BackendError as exc:
        print(f"momus bench: {exc}", file=sys.stderr)
        return 1
    paths = sorted(Path(p) for p in (args.files or glob.glob(DEFAULT_SAMPLES)))
    if not paths:
        print("momus bench: no files to run on", file=sys.stderr)
        return 1
    run_comparison(
        list(args.models or DEFAULT_MODELS),
        paths,
        settings,
        args.mode,
        Path(args.out),
        notes=args.notes,
        unload=not args.keep_loaded,
    )
    return 0
