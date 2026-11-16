# Tests for the benchmark engine (plan §11). No model and no Ollama are used.

import json
import types

import pytest

from momus import bench
from momus.backends import BackendError
from momus.backends.fake import FakeBackend
from momus.cli import build_parser
from momus.config import LocalSettings

TWO_FUNCTIONS = "def a():\n    return 1\n\n\ndef b():\n    return 2\n"


# A fake that also reports token counts, like a real server does.
class UsageBackend:
    def __init__(self, replies):
        self.inner = FakeBackend(replies)
        self.last_usage = None

    def complete(self, prompt):
        reply = self.inner.complete(prompt)
        self.last_usage = {"prompt_tokens": 10, "completion_tokens": 5}
        return reply


# Stands in for OllamaInfo and records what the benchmark asked of it.
class StubOllama:
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
    assert len(run.requests) == 3  # two functions and the file itself


def test_summary_counts_and_the_main_metric(tmp_path):
    path = sample(tmp_path)
    run = bench.run_model("m1", UsageBackend(["DOCSTRING:\nFirst.", "junk"]), [path], "docstrings", {})
    stats = bench.summarize(run)
    # The fake repeats its last reply, so the file's own docstring is rejected too.
    assert stats["docstrings_added"] == 1 and stats["docstrings_rejected"] == 2
    assert stats["rejected_by_cause"] == {"reply": 2}
    assert stats["accepted_total"] == 1 and stats["guard_acceptance"] == 1.0
    assert stats["requests"] == 3 and stats["requests_failed"] == 0
    assert stats["prompt_tokens"] == 30 and stats["completion_tokens"] == 15
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
    assert data["summary"]["accepted_total"] == 3  # the fake repeats its one reply: two functions and the file
    assert data["requests"][0]["prompt"] and data["requests"][0]["reply"].startswith("DOCSTRING")
    text = md_path.read_text()
    assert "## Conditions" in text and "power_source: mains" in text and "```diff" in text


def test_a_model_that_was_not_run_says_so(tmp_path):
    run = bench.ModelRun("ghost:1b", {}, "both", skipped_reason="not installed")
    json_path, md_path = bench.write_run(run, tmp_path)
    assert json.loads(json_path.read_text())["skipped_reason"] == "not installed"
    assert "**Not run:** not installed" in md_path.read_text()


# --- The reviewer (plan §11: "comments flagged by the reviewer") ------------


# Clio writes "First." for both functions and the file; the reviewer flags C1.
def reviewed_run(tmp_path, review_replies=("C1: Says nothing.",)):
    path = sample(tmp_path)
    reviewer = bench.Reviewer(UsageBackend(list(review_replies)))
    run = bench.run_model("m1", UsageBackend(["DOCSTRING:\nFirst."]), [path], "docstrings", {}, reviewer)
    return run, reviewer, path


def test_without_a_reviewer_the_review_figures_are_empty_not_zero(tmp_path):
    run = bench.run_model("m1", UsageBackend(["DOCSTRING:\nFirst."]), [sample(tmp_path)], "docstrings", {})
    stats = bench.summarize(run)
    assert not run.reviewed and run.files[0].findings == []
    assert stats["flagged_by_reviewer"] is None and stats["review_requests"] is None
    assert "not reviewed" in bench.render_markdown(run, stats)


def test_the_reviewer_reads_what_the_model_wrote_and_its_findings_are_counted(tmp_path):
    run, reviewer, path = reviewed_run(tmp_path)
    assert path.read_text() == TWO_FUNCTIONS  # still a dry run
    assert run.reviewed and run.comments_reviewed == 3
    (finding,) = run.files[0].findings
    assert (finding["line"], finding["kind"], finding["problem"]) == (1, "docstring", "Says nothing.")
    # The reviewer was shown the generated docstrings, not the original file.
    assert '+|     """First."""' in reviewer.requests[0].prompt
    stats = bench.summarize(run)
    assert (stats["flagged_by_reviewer"], stats["comments_reviewed"]) == (1, 3)
    assert stats["accepted_total"] == 3 and stats["accepted_not_flagged"] == 2


def test_the_review_is_counted_apart_from_the_local_model(tmp_path):
    run, _, _ = reviewed_run(tmp_path)
    stats = bench.summarize(run)
    assert (stats["requests"], stats["prompt_tokens"]) == (3, 30)  # Clio only
    assert (stats["review_requests"], stats["review_prompt_tokens"], stats["review_completion_tokens"]) == (1, 10, 5)


def test_a_review_that_fails_is_recorded_and_the_run_survives(tmp_path):
    run, _, _ = reviewed_run(tmp_path, review_replies=["I liked it a lot."])
    stats = bench.summarize(run)
    assert run.reviewed and stats["flagged_by_reviewer"] == 0
    assert stats["review_errors"] == 1 and stats["comments_reviewed"] == 0
    assert "were **not** reviewed" in bench.render_markdown(run, stats)


def test_a_file_the_model_added_nothing_to_is_not_sent_to_the_reviewer(tmp_path):
    reviewer = bench.Reviewer(FakeBackend(["OK"]))
    run = bench.run_model("m1", FakeBackend(["junk"]), [sample(tmp_path)], "docstrings", {}, reviewer)
    assert run.reviewed and reviewer.requests == []
    assert bench.summarize(run)["flagged_by_reviewer"] == 0


def test_each_run_gets_only_its_own_review_requests(tmp_path):
    first, reviewer, path = reviewed_run(tmp_path)
    second = bench.run_model("m2", UsageBackend(["DOCSTRING:\nSecond."]), [path], "docstrings", {}, reviewer)
    assert len(reviewer.requests) == 2
    assert len(first.review_requests) == 1 and len(second.review_requests) == 1
    assert "Second." in second.review_requests[0].prompt


def test_short_files_go_to_the_small_review_model_and_are_still_recorded(tmp_path):
    main, small = FakeBackend(["OK"]), FakeBackend(["C2: Wrong."])
    reviewer = bench.Reviewer(main, small, small_file_lines=200)
    run = bench.run_model(
        "m1", UsageBackend(["DOCSTRING:\nFirst."]), [sample(tmp_path)], "docstrings", {}, reviewer
    )
    assert main.prompts == [] and len(small.prompts) == 1
    assert len(run.review_requests) == 1 and len(run.files[0].findings) == 1


def test_result_files_carry_the_findings_and_the_review_cost(tmp_path):
    run, _, _ = reviewed_run(tmp_path)
    json_path, md_path = bench.write_run(run, tmp_path / "out")
    data = json.loads(json_path.read_text())
    assert data["files"][0]["findings"][0]["problem"] == "Says nothing."
    assert data["summary"]["flagged_by_reviewer"] == 1 and len(data["review_requests"]) == 1
    text = md_path.read_text()
    assert "## Flagged by the reviewer" in text
    assert "- `sample.py:1` (docstring): Says nothing." in text
    (row,) = [line for line in text.splitlines() if line.startswith("| sample.py |")]
    assert row.endswith("| 3 | 0 | 0 | 1 |")  # added, rejected, skipped, flagged


def test_the_comparison_reviews_every_model_and_says_which_reviewer(tmp_path):
    reviewer = bench.Reviewer(FakeBackend(["OK"]), description={"backend": "fake", "model": "strong"})
    runs = bench.run_comparison(
        ["m1", "m2"], [sample(tmp_path)], LocalSettings(), "docstrings", tmp_path / "out",
        ollama=StubOllama(), make_backend=lambda s: FakeBackend(["DOCSTRING:\nDoc."]),
        log=lambda *a: None, reviewer=reviewer,
    )
    assert all(run.reviewed and run.comments_reviewed == 3 for run in runs)
    assert runs[0].conditions["reviewer"] == {"backend": "fake", "model": "strong"}
    unreviewed = bench.run_comparison(
        ["m1"], [sample(tmp_path)], LocalSettings(), "docstrings", tmp_path / "out2",
        ollama=StubOllama(), make_backend=lambda s: FakeBackend(["junk"]), log=lambda *a: None,
    )
    assert "none" in unreviewed[0].conditions["reviewer"] and not unreviewed[0].reviewed


def test_the_reviewer_is_built_from_the_review_settings():
    from momus.config import ReviewSettings

    reviewer = bench.Reviewer.from_settings(ReviewSettings(small_file_lines=120, max_items=4))
    assert (reviewer.small_file_lines, reviewer.max_items) == (120, 4)
    assert reviewer.small_backend is not None and reviewer.small_backend.requests is reviewer.requests
    assert reviewer.description["model"] == "sonnet" and reviewer.description["small_model"] == "haiku"


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
    assert (args.models, args.keep_loaded, args.notes, args.mode) == (["a", "b"], True, "x", "docstrings")
    assert args.review is False
    assert build_parser().parse_args(["bench", "--review"]).review is True


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
