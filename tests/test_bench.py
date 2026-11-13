"""Tests for the benchmark engine (plan §11). No model and no Ollama are used."""

import json
import types

import pytest

from momus import bench
from momus.backends import BackendError
from momus.backends.fake import FakeBackend
from momus.cli import build_parser
from momus.config import LocalSettings

TWO_FUNCTIONS = "def a():\n    return 1\n\n\ndef b():\n    return 2\n"


class UsageBackend:
    """A fake that also reports token counts, like a real server does."""

    def __init__(self, replies):
        self.inner = FakeBackend(replies)
        self.last_usage = None

    def complete(self, prompt):
        reply = self.inner.complete(prompt)
        self.last_usage = {"prompt_tokens": 10, "completion_tokens": 5}
        return reply


class StubOllama:
    """Stands in for OllamaInfo and records what the benchmark asked of it."""

    def __init__(self, installed=None):
        self._installed = installed
        self.unloads = 0

    def version(self):
        return "9.9.9"

    def installed(self):
        return self._installed

    def loaded(self):
        return [{"name": "m1", "context_length": 4096}]

    def details(self, model):
        return {"quantization_level": "Q4_K_M"}

    def unload_all(self):
        self.unloads += 1
        return ["something"]


def sample(tmp_path, text=TWO_FUNCTIONS):
    path = tmp_path / "sample.py"
    path.write_text(text)
    return path


# --- Recording -------------------------------------------------------------


def test_recording_backend_keeps_prompts_replies_seconds_and_usage():
    recorder = bench.RecordingBackend(UsageBackend(["hello"]))
    assert recorder.complete("question") == "hello"
    (request,) = recorder.requests
    assert (request.prompt, request.reply, request.completion_tokens) == ("question", "hello", 5)
    assert request.seconds >= 0 and request.error is None


def test_recording_backend_records_a_failure_and_still_raises():
    class Down:
        def complete(self, prompt):
            raise BackendError("server is down")

    recorder = bench.RecordingBackend(Down())
    with pytest.raises(BackendError):
        recorder.complete("question")
    assert recorder.requests[0].error == "server is down" and recorder.requests[0].reply is None


# --- Running and summarizing -----------------------------------------------


def test_run_model_is_a_dry_run_and_records_outcomes_with_kind_and_cause(tmp_path):
    path = sample(tmp_path)
    before = path.read_bytes()
    backend = UsageBackend(["DOCSTRING:\nFirst.", "no marker at all"])
    run = bench.run_model("m1", backend, [path], "docstrings", {})
    assert path.read_bytes() == before  # the benchmark never writes the files it reads
    outcomes = {o["name"]: o for o in run.files[0].outcomes}
    assert (outcomes["a"]["kind"], outcomes["a"]["status"]) == ("docstring", "added")
    assert (outcomes["b"]["status"], outcomes["b"]["cause"]) == ("rejected", "reply")
    assert '+    """First."""' in run.files[0].diff
    assert len(run.requests) == 2


def test_summary_counts_and_the_main_metric(tmp_path):
    path = sample(tmp_path)
    run = bench.run_model("m1", UsageBackend(["DOCSTRING:\nFirst.", "junk"]), [path], "docstrings", {})
    stats = bench.summarize(run)
    assert stats["docstrings_added"] == 1 and stats["docstrings_rejected"] == 1
    assert stats["rejected_by_cause"] == {"reply": 1}
    assert stats["accepted_total"] == 1 and stats["guard_acceptance"] == 1.0
    assert stats["requests"] == 2 and stats["requests_failed"] == 0
    assert stats["prompt_tokens"] == 20 and stats["completion_tokens"] == 10
    assert stats["tokens_per_second"] > 0 and stats["accepted_per_minute"] > 0


def test_summary_without_token_counts_leaves_them_empty(tmp_path):
    run = bench.run_model("m1", FakeBackend(["junk"]), [sample(tmp_path)], "docstrings", {})
    stats = bench.summarize(run)
    assert stats["tokens_per_second"] is None and stats["completion_tokens"] is None


def test_unreadable_file_is_recorded_not_fatal(tmp_path):
    run = bench.run_model("m1", FakeBackend(), [tmp_path / "missing.py"], "both", {})
    assert run.files[0].error.startswith("cannot read")
    assert bench.summarize(run)["files_unreadable"] == 1


# --- Conditions ------------------------------------------------------------


def test_machine_conditions_never_raise_and_carry_the_notes():
    conditions = bench.collect_machine_conditions("everything else closed")
    for key in ("cpu", "power_source", "power_profile", "ram_available_gb_at_start", "momus_commit"):
        assert key in conditions
    assert conditions["operator_notes"] == "everything else closed"


def test_ollama_info_degrades_quietly_when_nothing_answers():
    info = bench.OllamaInfo("http://127.0.0.1:9/v1", timeout=1)
    assert info.root == "http://127.0.0.1:9"
    assert info.version() is None and info.installed() is None and info.details("m") is None
    assert info.loaded() == [] and info.unload_all() == []


# --- Result files ----------------------------------------------------------


def test_write_run_saves_raw_json_and_readable_markdown(tmp_path):
    run = bench.run_model(
        "qwen2.5-coder:7b", UsageBackend(["DOCSTRING:\nFirst."]), [sample(tmp_path)], "docstrings",
        {"power_source": "mains"},
    )
    json_path, md_path = bench.write_run(run, tmp_path / "out")
    assert json_path.name.endswith("_qwen2.5-coder-7b.json")
    data = json.loads(json_path.read_text())
    assert data["conditions"]["power_source"] == "mains"
    assert data["summary"]["accepted_total"] == 2  # the fake repeats its one reply for both functions
    assert data["requests"][0]["prompt"] and data["requests"][0]["reply"].startswith("DOCSTRING")
    text = md_path.read_text()
    assert "## Conditions" in text and "power_source: mains" in text and "```diff" in text


def test_a_model_that_was_not_run_says_so(tmp_path):
    run = bench.ModelRun("ghost:1b", {}, "both", skipped_reason="not installed")
    json_path, md_path = bench.write_run(run, tmp_path)
    assert json.loads(json_path.read_text())["skipped_reason"] == "not installed"
    assert "**Not run:** not installed" in md_path.read_text()


# --- The comparison --------------------------------------------------------


def test_comparison_skips_models_that_are_not_installed_and_unloads_between(tmp_path):
    built = []

    def make_backend(settings):
        built.append(settings.model)
        return FakeBackend(["junk"])

    ollama = StubOllama(installed=["m1"])
    runs = bench.run_comparison(
        ["m1", "ghost"], [sample(tmp_path)], LocalSettings(), "docstrings", tmp_path / "out",
        notes="n", ollama=ollama, make_backend=make_backend, log=lambda *a: None,
    )
    assert built == ["m1"]
    assert runs[1].skipped_reason and not runs[0].skipped_reason
    assert ollama.unloads == 1
    assert runs[0].conditions["ollama_version"] == "9.9.9"
    assert runs[0].conditions["unloaded_before_run"] == ["something"]
    assert runs[0].conditions["context_length_seen"] == 4096
    assert "power_source_at_end" in runs[0].conditions
    assert len(list((tmp_path / "out").glob("*.json"))) == 2


def test_keep_loaded_does_not_unload(tmp_path):
    ollama = StubOllama(installed=None)  # not Ollama, or silent: nothing is skipped
    bench.run_comparison(
        ["m1"], [sample(tmp_path)], LocalSettings(), "docstrings", tmp_path / "out",
        unload=False, ollama=ollama, make_backend=lambda s: FakeBackend(["junk"]),
        log=lambda *a: None,
    )
    assert ollama.unloads == 0


# --- Command line ----------------------------------------------------------


def test_bench_options_are_parsed():
    args = build_parser().parse_args(["bench", "--models", "a", "b", "--keep-loaded", "--notes", "x"])
    assert (args.models, args.keep_loaded, args.notes, args.mode) == (["a", "b"], True, "x", "both")


def test_main_refuses_to_run_without_files(tmp_path, capsys):
    args = types.SimpleNamespace(
        config=tmp_path / "none.toml", files=[], models=None, mode="both", out=tmp_path,
        notes="", keep_loaded=False,
    )
    old = bench.DEFAULT_SAMPLES
    bench.DEFAULT_SAMPLES = str(tmp_path / "nothing-*.py")
    try:
        assert bench.main(args) == 1
    finally:
        bench.DEFAULT_SAMPLES = old
    assert "no files" in capsys.readouterr().err
