"""Tests for the review stage (plan §10): critic, Claude backends, config, command.

Only fake backends, a fake process runner and a stub HTTP server on localhost
are used: no real API and no real model.
"""

import io
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from momus import critic
from momus.backends import BackendError
from momus.backends.anthropic import AnthropicBackend
from momus.backends.claude_code import ClaudeCodeBackend
from momus.backends.fake import FakeBackend
from momus.cli import build_parser, review_command
from momus.config import (
    ReviewSettings,
    build_review_backend,
    load_review_settings,
)
from momus.critic import Comment, CriticError, Group

ORIGINAL = (
    "def add(a, b):\n"
    "    total = a + b\n"
    "    return total\n"
    "\n"
    "\n"
    "def scale(values, factor):\n"
    "    return [v * factor for v in values]\n"
)
NEW = (
    "def add(a, b):\n"
    '    """Return the sum of a and b."""\n'
    "    # Keep the sum in a name so it can be inspected.\n"
    "    # It is returned unchanged.\n"
    "    total = a + b\n"
    "    return total\n"
    "\n"
    "\n"
    "# Helper used by the report.\n"
    "def scale(values, factor):\n"
    "    return [v * factor for v in values]\n"
)


# --- Finding what was added ------------------------------------------------


def test_added_docstring_and_comment_blocks_are_found_with_their_lines():
    comments = critic.find_comments("m.py", ORIGINAL, NEW)
    assert [(c.kind, c.line, c.end_line) for c in comments] == [
        ("docstring", 2, 2),
        ("comment", 3, 4),
        ("comment", 9, 9),
    ]
    assert comments[0].text == '"""Return the sum of a and b."""'
    assert comments[1].text == "Keep the sum in a name so it can be inspected. It is returned unchanged."


def test_multiline_docstring_is_one_comment():
    original = "def f():\n    return 1\n"
    new = 'def f():\n    """Line one.\n\n    Line two.\n    """\n    return 1\n'
    (comment,) = critic.find_comments("m.py", original, new)
    assert (comment.kind, comment.line, comment.end_line) == ("docstring", 2, 5)


def test_identical_files_have_nothing_to_review():
    assert critic.find_comments("m.py", ORIGINAL, ORIGINAL) == []


@pytest.mark.parametrize(
    "new",
    [
        NEW.replace("total = a + b", "result = a + b"),  # a renamed variable
        NEW.replace("a + b\n    return total", "a+b\n    return total"),  # a reformatted line
        NEW.replace("    return total\n", ""),  # a removed line
        NEW + "print('extra')\n",  # added code
    ],
)
def test_a_change_that_is_not_comments_only_is_refused(new):
    with pytest.raises(CriticError):
        critic.find_comments("m.py", ORIGINAL, new)


def test_a_hash_line_added_inside_a_string_is_not_a_comment_and_is_refused():
    # Only the Argus checks can tell: the added line looks like a comment, but it
    # sits inside a string literal and changes the string's value.
    original = 'TEXT = """first\nsecond"""\n'
    new = 'TEXT = """first\n# not a comment\nsecond"""\n'
    with pytest.raises(CriticError, match="not a comments-only change"):
        critic.find_comments("m.py", original, new)


# --- Showing the code around them ------------------------------------------


def test_comments_in_one_function_share_one_copy_of_its_code():
    groups = critic.build_groups("m.py", ORIGINAL, NEW)
    assert [len(g.comments) for g in groups] == [2, 1]
    code = groups[0].code
    assert '    1 | def add(a, b):' in code
    assert '    2+|     """Return the sum of a and b."""' in code  # added: marked with +
    assert "    5 |     total = a + b" in code  # the author's code is there, unmarked
    assert "scale" not in code


def test_comment_outside_any_function_gets_a_window_around_it():
    group = critic.build_groups("m.py", ORIGINAL, NEW)[1]
    assert "    9+| # Helper used by the report." in group.code
    assert "def scale" in group.code


def test_a_very_long_function_is_shown_only_near_its_comment():
    original = "def big():\n" + "".join(f"    x{i} = {i}\n" for i in range(100))
    lines = original.splitlines(keepends=True)
    new = "".join(lines[:50] + ["    # Why x49 is next.\n"] + lines[50:])
    (group,) = critic.build_groups("m.py", original, new)
    assert "x49 = 49" in group.code and "Why x49" in group.code
    assert "x0 = 0" not in group.code and "x99" not in group.code
    assert len(group.code.splitlines()) <= 2 * critic.CONTEXT_MARGIN + 3


# --- Batches and replies ---------------------------------------------------


def make_group(n: int) -> Group:
    comment = Comment("m.py", "comment", n, n, f"text {n}")
    return Group("m.py", f"{n:>5}+| # text {n}", (comment,))


def test_batches_hold_at_most_max_items_and_number_comments_from_one():
    batches = critic.build_batches([make_group(n) for n in range(1, 6)], max_items=2)
    assert [len(b.comments) for b in batches] == [2, 2, 1]
    assert all(sorted(b.comments) == list(range(1, len(b.comments) + 1)) for b in batches)
    assert "C1 (line 3, comment): text 3" in batches[1].prompt
    assert "{{BODY}}" not in batches[0].prompt and "reply with the single" in batches[0].prompt


def test_a_batch_also_stops_growing_when_its_code_is_too_long(monkeypatch):
    monkeypatch.setattr(critic, "MAX_BATCH_CHARS", 30)
    assert len(critic.build_batches([make_group(n) for n in range(1, 4)], max_items=10)) == 3


def test_no_groups_means_no_requests():
    assert critic.build_batches([], 10) == []


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("OK", []),
        ("ok.", []),
        ("C2: Says it returns a list, but it returns a dict.", [(2, "Says it returns a list, but it returns a dict.")]),
        ("C1) Redundant.\nC3 - False.", [(1, "Redundant."), (3, "False.")]),
        ("<think>hmm</think>\nC1: Redundant.", [(1, "Redundant.")]),
        ("```\nC1: Redundant.\n```", [(1, "Redundant.")]),
    ],
)
def test_findings_are_read_from_the_reply(reply, expected):
    assert critic.parse_findings(reply) == expected


@pytest.mark.parametrize("bad", ["Looks good to me!", "The comments are mostly fine but C1 is odd."])
def test_a_reply_in_neither_format_is_refused(bad):
    with pytest.raises(CriticError):
        critic.parse_findings(bad)


# --- Reviewing -------------------------------------------------------------


def test_a_finding_points_at_the_file_and_line_of_the_comment():
    backend = FakeBackend(["C2: Says nothing the code does not."])
    result = critic.review_changes([("m.py", ORIGINAL, NEW)], backend)
    (finding,) = result.findings
    assert str(finding) == "m.py:3: Says nothing the code does not."
    assert (finding.kind, result.reviewed, result.batches, result.errors) == ("comment", 3, 1, [])
    assert "total = a + b" in backend.prompts[0]  # the code is in the request, not only the comment


def test_ok_means_reviewed_with_no_findings():
    result = critic.review_changes([("m.py", ORIGINAL, NEW)], FakeBackend(["OK"]))
    assert (result.findings, result.reviewed, result.errors) == ([], 3, [])


def test_a_refused_change_does_not_stop_the_others():
    bad = NEW.replace("total = a + b", "result = a + b")
    backend = FakeBackend(["OK"])
    result = critic.review_changes([("bad.py", ORIGINAL, bad), ("good.py", ORIGINAL, NEW)], backend)
    assert result.reviewed == 3 and len(backend.prompts) == 1
    assert len(result.errors) == 1 and result.errors[0].startswith("bad.py: not a comments-only change")


def test_unchanged_files_cost_no_request():
    backend = FakeBackend(["OK"])
    result = critic.review_changes([("m.py", ORIGINAL, ORIGINAL)], backend)
    assert backend.prompts == [] and result.reviewed == 0 and result.errors == []


def test_batches_split_a_large_review_into_several_requests():
    backend = FakeBackend(["OK"])
    result = critic.review_changes([("m.py", ORIGINAL, NEW)], backend, max_items=2)
    assert len(backend.prompts) == result.batches == 2


def test_backend_failure_and_bad_reply_are_recorded_not_raised():
    class Down:
        def complete(self, prompt):
            raise BackendError("server is down")

    down = critic.review_changes([("m.py", ORIGINAL, NEW)], Down())
    assert down.reviewed == 0 and "server is down" in down.errors[0]
    junk = critic.review_changes([("m.py", ORIGINAL, NEW)], FakeBackend(["Looks fine!"]))
    assert junk.reviewed == 0 and "neither OK nor" in junk.errors[0]


def test_a_finding_about_an_unknown_comment_is_reported_as_an_error():
    result = critic.review_changes([("m.py", ORIGINAL, NEW)], FakeBackend(["C9: Wrong."]))
    assert result.findings == [] and "unknown comment C9" in result.errors[0]


def test_findings_come_out_sorted_by_file_and_line():
    backend = FakeBackend(["C3: b.", "C1: a.", "C3: b2."])
    result = critic.review_changes(
        [("z.py", ORIGINAL, NEW), ("a.py", ORIGINAL, NEW)], backend, max_items=3
    )
    keys = [(f.path, f.line) for f in result.findings]
    assert keys == sorted(keys)


# --- The baseline from git -------------------------------------------------


def git(folder: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(folder), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        check=True,
        capture_output=True,
    )


def test_baseline_is_read_from_git(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "m.py").write_bytes(ORIGINAL.replace("\n", "\r\n").encode())
    git(tmp_path, "add", "m.py")
    git(tmp_path, "commit", "-q", "-m", "x")
    (tmp_path / "m.py").write_text(NEW)
    assert critic.read_git_baseline(tmp_path / "m.py") == ORIGINAL.replace("\n", "\r\n")


def test_missing_baseline_is_an_error_not_a_crash(tmp_path):
    with pytest.raises(CriticError):
        critic.read_git_baseline(tmp_path / "not-in-a-repo.py")
    git(tmp_path, "init", "-q")
    (tmp_path / "new.py").write_text("x = 1\n")
    with pytest.raises(CriticError, match="no baseline"):
        critic.read_git_baseline(tmp_path / "new.py")


# --- The command -----------------------------------------------------------


def run_review(tmp_path, backend, baseline=ORIGINAL, text=NEW):
    path = tmp_path / "m.py"
    path.write_text(text)
    out = io.StringIO()
    status = review_command([path], backend, read_baseline=lambda p, ref: baseline, out=out)
    return status, out.getvalue(), path


def test_command_prints_one_line_per_problem_and_nothing_else(tmp_path, capsys):
    status, out, path = run_review(tmp_path, FakeBackend(["C2: Redundant."]))
    assert status == 0 and out == f"{path}:3: Redundant.\n"
    assert capsys.readouterr().err == ""
    assert path.read_text() == NEW  # review never edits the file


def test_command_with_no_added_comments_says_so_on_stderr(tmp_path, capsys):
    status, out, _ = run_review(tmp_path, FakeBackend(["OK"]), text=ORIGINAL)
    assert (status, out) == (0, "")
    assert "no added comments to review" in capsys.readouterr().err


def test_command_reports_files_it_could_not_review(tmp_path, capsys):
    def no_baseline(path, ref):
        raise CriticError("no baseline at HEAD")

    path = tmp_path / "m.py"
    path.write_text(NEW)
    assert review_command([path], FakeBackend(["OK"]), read_baseline=no_baseline) == 1
    assert "cannot review: no baseline at HEAD" in capsys.readouterr().err
    refused = run_review(tmp_path, FakeBackend(["OK"]), text=NEW.replace("a + b", "a - b"))[0]
    assert refused == 1


def test_review_options_are_parsed():
    args = build_parser().parse_args(["review", "a.py", "b.py", "--base", "HEAD~2"])
    assert (args.files, args.base) == ([Path("a.py"), Path("b.py")], "HEAD~2")


# --- Claude Code backend ---------------------------------------------------


def claude_json(result="the reply", is_error=False, **usage) -> str:
    """What ``claude -p --output-format json`` prints."""
    counts = {"input_tokens": 2, "cache_creation_input_tokens": 1200, "cache_read_input_tokens": 70, "output_tokens": 9}
    return json.dumps({"result": result, "is_error": is_error, "usage": {**counts, **usage}, "total_cost_usd": 0.01})


class Runner:
    """A stand-in for ``subprocess.run`` that records how it was called."""

    def __init__(self, stdout=None, returncode=0, stderr="", raises=None):
        stdout = claude_json() if stdout is None else stdout
        self.result = subprocess.CompletedProcess([], returncode, stdout, stderr)
        self.raises = raises
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if self.raises:
            raise self.raises
        return self.result


def test_claude_code_runs_print_mode_with_the_prompt_on_stdin():
    runner = Runner()
    assert ClaudeCodeBackend(model="some-model", runner=runner).complete("question") == "the reply"
    (args, kwargs), = runner.calls
    assert args[:2] == ["claude", "-p"]
    assert args[args.index("--model") + 1] == "some-model"
    assert kwargs["input"] == "question"
    assert Path(kwargs["cwd"]).name.startswith("momus-review-")  # not the project folder
    assert not Path(kwargs["cwd"]).exists()  # and cleaned up afterwards


def test_claude_code_switches_off_everything_that_inflates_a_request():
    # Without these, one request carried about 186 000 input tokens (measured
    # 2026-11-14): the default system prompt, every tool server, every skill.
    runner = Runner()
    ClaudeCodeBackend(runner=runner).complete("q")
    args = runner.calls[0][0]
    assert args[args.index("--tools") + 1] == ""  # an empty list turns every built-in tool off
    assert "--strict-mcp-config" in args and "--mcp-config" not in args  # no tool servers at all
    assert "--disable-slash-commands" in args
    assert "--no-session-persistence" in args
    assert args[args.index("--system-prompt") + 1].startswith("You review code comments")
    assert args[args.index("--output-format") + 1] == "json"


def test_claude_code_without_a_model_leaves_the_choice_to_claude():
    runner = Runner()
    ClaudeCodeBackend(runner=runner).complete("q")
    assert "--model" not in runner.calls[0][0]


def test_claude_code_reports_the_tokens_the_call_used():
    backend = ClaudeCodeBackend(runner=Runner())
    assert backend.last_usage is None
    backend.complete("q")
    # Cached tokens are input too: leaving them out would hide most of the cost.
    assert backend.last_usage == {"prompt_tokens": 1272, "completion_tokens": 9, "cost_usd": 0.01}


@pytest.mark.parametrize(
    ("runner", "message"),
    [
        (Runner(raises=FileNotFoundError()), "command not found"),
        (Runner(raises=subprocess.TimeoutExpired("claude", 1)), "did not answer"),
        (Runner(raises=PermissionError("no")), "cannot run"),
        (Runner(returncode=2, stderr="not logged in"), "status 2: not logged in"),
        (Runner(stdout="plain text, not JSON"), "did not return JSON"),
        (Runner(stdout="[1, 2]"), "unexpected reply"),
        (Runner(stdout=claude_json(result="rate limited", is_error=True)), "reported an error: rate limited"),
        (Runner(stdout=claude_json(result="  ")), "returned no text"),
    ],
)
def test_claude_code_failures_become_backend_errors(runner, message):
    with pytest.raises(BackendError, match=message):
        ClaudeCodeBackend(runner=runner).complete("q")


# --- Anthropic backend -----------------------------------------------------


class StubApi:
    """A localhost server that returns one fixed response and records the request."""

    def __init__(self, status=200, body=b""):
        self.seen = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                outer.seen.append((dict(self.headers), json.loads(self.rfile.read(length))))
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_port}/v1/messages"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()


def test_anthropic_sends_the_key_from_the_environment_and_returns_the_text(monkeypatch):
    monkeypatch.setenv("MOMUS_TEST_KEY", "sk-test-123")
    body = json.dumps(
        {"content": [{"type": "text", "text": "C1: "}, {"type": "text", "text": "False."}]}
    ).encode()
    with StubApi(body=body) as api:
        backend = AnthropicBackend("some-model", "MOMUS_TEST_KEY", max_tokens=64, url=api.url)
        assert backend.complete("question") == "C1: False."
    (headers, payload), = api.seen
    headers = {name.lower(): value for name, value in headers.items()}  # urllib capitalizes names
    assert headers["x-api-key"] == "sk-test-123" and headers["anthropic-version"]
    assert payload == {
        "model": "some-model",
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "question"}],
    }


def test_anthropic_without_a_key_fails_before_any_request(monkeypatch):
    monkeypatch.delenv("MOMUS_TEST_KEY", raising=False)
    with StubApi(body=b"{}") as api:
        with pytest.raises(BackendError, match="MOMUS_TEST_KEY is not set"):
            AnthropicBackend("m", "MOMUS_TEST_KEY", url=api.url).complete("q")
    assert api.seen == []


@pytest.mark.parametrize(
    ("status", "body", "message"),
    [
        (401, b'{"error": "invalid x-api-key"}', "HTTP 401"),
        (200, b"not json", "not valid JSON"),
        (200, b"{}", "no content blocks"),
        (200, b'{"content": []}', "no text"),
    ],
)
def test_anthropic_errors_become_backend_errors_without_leaking_the_key(
    monkeypatch, status, body, message
):
    monkeypatch.setenv("MOMUS_TEST_KEY", "sk-secret-value")
    with StubApi(status, body) as api:
        with pytest.raises(BackendError, match=message) as excinfo:
            AnthropicBackend("m", "MOMUS_TEST_KEY", url=api.url).complete("q")
    assert "sk-secret-value" not in str(excinfo.value)


# --- Settings --------------------------------------------------------------


def test_review_settings_defaults_and_overrides(tmp_path):
    assert load_review_settings(tmp_path / "none.toml") == ReviewSettings()
    path = tmp_path / "momus.toml"
    path.write_text('[review]\nbackend = "anthropic"\nmodel = "m"\nmax_items = 4\n')
    settings = load_review_settings(path)
    assert (settings.backend, settings.model, settings.max_items) == ("anthropic", "m", 4)


@pytest.mark.parametrize(
    "text",
    ['[review]\nbackend = "carrier-pigeon"\n', "[review]\nnum_ctx = 1\n", "[review\n"],
)
def test_bad_review_settings_are_rejected(tmp_path, text):
    path = tmp_path / "momus.toml"
    path.write_text(text)
    with pytest.raises(BackendError):
        load_review_settings(path)


def test_the_right_backend_is_built_from_the_settings():
    assert isinstance(build_review_backend(ReviewSettings()), ClaudeCodeBackend)
    assert build_review_backend(ReviewSettings()).model is None
    anthropic = build_review_backend(ReviewSettings(backend="anthropic", model="m"))
    assert isinstance(anthropic, AnthropicBackend) and anthropic.api_key_env == "ANTHROPIC_API_KEY"
    with pytest.raises(BackendError, match="model is required"):
        build_review_backend(ReviewSettings(backend="anthropic"))


def test_the_shipped_example_config_has_a_valid_review_table():
    assert load_review_settings("momus.toml").backend == "claude_code"


# --- Code that is shown only in part ---------------------------------------


def test_a_cut_class_says_what_was_left_out_and_lists_the_method_signatures():
    body = "".join(f"    def method_{i}(self, value):\n        return value + {i}\n\n" for i in range(30))
    original = "class Big:\n    limit = 5\n\n" + body
    new = original.replace("class Big:\n", 'class Big:\n    """Hold thirty methods."""\n', 1)
    (group,) = critic.build_groups("m.py", original, new)
    assert "of this definition are not shown; the signatures of its methods there:" in group.code
    assert "def method_29(self, value):" in group.code  # far below the window, still listed
    assert "return value + 29" not in group.code  # but not its body
    assert len(group.code.splitlines()) < 60


def test_a_cut_function_says_which_lines_were_left_out_at_both_ends():
    original = "def big():\n" + "".join(f"    x{i} = {i}\n" for i in range(100))
    lines = original.splitlines(keepends=True)
    new = "".join(lines[:50] + ["    # Why x49 is next.\n"] + lines[50:])
    (group,) = critic.build_groups("m.py", original, new)
    assert "... lines 1-38 of this definition are not shown" in group.code
    assert "... lines 64-102 of this definition are not shown" in group.code


def test_a_definition_shown_whole_has_no_omission_note():
    assert "not shown" not in critic.build_groups("m.py", ORIGINAL, NEW)[0].code


def test_the_prompt_tells_the_reviewer_not_to_report_what_it_cannot_see():
    prompt = critic.build_batches(critic.build_groups("m.py", ORIGINAL, NEW))[0].prompt
    assert "Never report something as missing" in prompt
