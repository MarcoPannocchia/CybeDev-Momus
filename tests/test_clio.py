"""Tests for Clio, docstring-only slice (plan §9). Only the fake backend is used."""

import ast
import io
import textwrap

import pytest

from momus import argus, clio
from momus.backends import BackendError
from momus.backends.fake import FakeBackend
from momus.cli import comment_command
from momus.clio import ADDED, REJECTED, SKIPPED, ClioError, parse_reply

SOURCE = textwrap.dedent(
    """
    def add(a, b):
        return a + b


    class Box:
        step = 1

        @property
        def size(self):
            return self.step

        def grow(self):
            self.step += 1
    """
).lstrip("\n")


def docs(source, backend):
    """Slice 1: docstrings only."""
    return clio.comment_source(source, backend, mode="docstrings")


def reply(text: str) -> str:
    return f"DOCSTRING:\n{text}"


def statuses(result) -> dict[str, str]:
    return {outcome.name: outcome.status for outcome in result.outcomes}


def docstrings(text: str) -> dict[str, str | None]:
    tree = ast.parse(text)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found[node.name] = ast.get_docstring(node)
    return found


# --- Reply parsing and layout ----------------------------------------------


def test_parse_reply_takes_the_text_after_the_marker():
    assert parse_reply("DOCSTRING:\nAdd two numbers.") == "Add two numbers."
    assert parse_reply("docstring: Add two numbers.") == "Add two numbers."


def test_parse_reply_strips_fences_chatter_and_quotes():
    assert parse_reply('Sure!\n```\nDOCSTRING:\n"""Add two numbers."""\n```\nDone.') == (
        "Add two numbers."
    )


def test_parse_reply_drops_code_the_model_repeated_after_its_answer():
    # Observed with qwen2.5-coder:1.5b on examples/retry.py (2026-11-12).
    echoed = "DOCSTRING:\nRetry a call.\n\nCode:\n```python\ndef f():\n    pass\n```"
    assert parse_reply(echoed) == "Retry a call."
    assert parse_reply("DOCSTRING:\nRetry a call.\n```python\ndef f(): pass\n```") == "Retry a call."


def test_parse_reply_ignores_reasoning_blocks():
    assert parse_reply("<think>\nhmm\n</think>\nDOCSTRING:\nDo it.") == "Do it."


def test_parse_reply_doubles_backslashes():
    assert parse_reply("DOCSTRING:\nSplit on \\n.") == "Split on \\\\n."


@pytest.mark.parametrize(
    "bad",
    ["Add two numbers.", "", "DOCSTRING:", 'DOCSTRING:\nSay """hi""" now.', "Here:\nDOCSTRING:\nx"],
)
def test_parse_reply_rejects_unusable_replies(bad):
    with pytest.raises(ClioError):
        parse_reply(bad)


def test_format_docstring_layouts():
    assert clio.format_docstring("One line.", "    ", "\n") == ['    """One line."""\n']
    assert clio.format_docstring("First.\n\nSecond.", "    ", "\n") == [
        '    """First.\n',
        "\n",
        "    Second.\n",
        '    """\n',
    ]
    # Text ending in a quote mark must not run into the closing quotes.
    assert clio.format_docstring('Say "hi"', "", "\n") == ['"""Say "hi"\n', '"""\n']


def test_prompt_contains_the_code_and_leaves_braces_alone():
    prompt = clio.build_prompt("function", "d = {1: 2}\n", "Some context.\n\n")
    assert "d = {1: 2}" in prompt and "Some context." in prompt and "{{" not in prompt


# --- Inserting docstrings --------------------------------------------------


def test_docstrings_are_added_to_functions_classes_and_methods():
    backend = FakeBackend([reply("Sum.")])
    result = docs(SOURCE, backend)
    assert statuses(result) == {
        "add": ADDED,
        "Box": ADDED,
        "Box.size": ADDED,
        "Box.grow": ADDED,
    }
    assert docstrings(result.text) == {"add": "Sum.", "Box": "Sum.", "size": "Sum.", "grow": "Sum."}
    assert len(backend.prompts) == 4


def test_result_passes_both_argus_checks_and_keeps_code_identical():
    result = docs(SOURCE, FakeBackend([reply("Doc.")]))
    assert result.changed
    assert argus.compare_code(SOURCE, result.text).accepted
    assert argus.check_inserted_lines(SOURCE, result.text, result.inserted_lines).accepted


def test_docstring_of_a_decorated_first_method_goes_above_the_decorator():
    result = docs(SOURCE, FakeBackend([reply("Doc.")]))
    lines = result.text.splitlines()
    box = lines.index("class Box:")
    assert lines[box + 1].strip() == '"""Doc."""'
    assert lines[box + 2] == "    step = 1"  # unchanged: the class has an attribute first
    size = lines.index("    def size(self):")
    assert lines[size - 1] == "    @property"
    assert lines[size + 1].strip() == '"""Doc."""'


def test_docstring_goes_before_a_decorator_when_it_is_the_first_statement():
    source = "class Box:\n    @property\n    def size(self):\n        return 1\n"
    result = docs(source, FakeBackend([reply("Doc.")]))
    assert result.text.splitlines()[:3] == ["class Box:", '    """Doc."""', "    @property"]
    assert argus.compare_code(source, result.text).accepted


def test_multiline_signature_and_indentation_are_handled():
    source = "def long(\n    a,\n    b,\n):\n    return a\n"
    result = docs(source, FakeBackend([reply("Return a.\n\nIgnore b.")]))
    assert docstrings(result.text)["long"] == "Return a.\n\nIgnore b."
    assert argus.check_inserted_lines(source, result.text, result.inserted_lines).accepted


# --- Ownership and safe skips ----------------------------------------------


def test_existing_docstring_is_never_replaced_and_the_model_is_not_asked():
    source = 'def add(a, b):\n    """Written by a person."""\n    return a + b\n'
    backend = FakeBackend([reply("Machine text.")])
    result = docs(source, backend)
    assert result.text == source and not result.changed
    assert statuses(result) == {"add": SKIPPED}
    assert backend.prompts == []


def test_body_on_the_def_line_is_left_alone():
    source = "def one(): return 1\n\ndef two():\n    return 2\n"
    result = docs(source, FakeBackend([reply("Doc.")]))
    assert statuses(result) == {"one": SKIPPED, "two": ADDED}
    assert "def one(): return 1" in result.text


def test_unparseable_file_is_returned_unchanged():
    backend = FakeBackend([reply("Doc.")])
    result = docs("def broken(:\n", backend)
    assert result.text == "def broken(:\n" and not result.changed
    assert backend.prompts == []


# --- Failures are contained ------------------------------------------------


def test_bad_reply_for_one_target_does_not_stop_the_others():
    backend = FakeBackend(["no marker here", reply("Doc.")])
    result = docs("def a():\n    pass\n\ndef b():\n    pass\n", backend)
    assert statuses(result) == {"a": REJECTED, "b": ADDED}
    assert docstrings(result.text) == {"a": None, "b": "Doc."}


def test_backend_failure_is_reported_not_raised():
    class Down:
        def complete(self, prompt):
            raise BackendError("server is down")

    result = docs(SOURCE, Down())
    assert result.text == SOURCE
    assert {o.status for o in result.outcomes} == {REJECTED}
    assert "server is down" in result.outcomes[0].reason


def test_insertion_that_fails_the_guard_is_dropped(monkeypatch):
    real = argus.check_inserted_lines
    monkeypatch.setattr(
        clio.argus,
        "check_inserted_lines",
        lambda original, new, inserted: real(original, new, [n + 1 for n in inserted]),
    )
    result = docs("def a():\n    pass\n", FakeBackend([reply("Doc.")]))
    assert result.text == "def a():\n    pass\n" and not result.changed
    assert statuses(result) == {"a": REJECTED}


# --- Byte-level care -------------------------------------------------------


def test_crlf_file_keeps_its_line_endings():
    source = SOURCE.replace("\n", "\r\n")
    result = docs(source, FakeBackend([reply("Doc.")]))
    assert result.changed
    assert "\n" not in result.text.replace("\r\n", "")
    assert argus.check_inserted_lines(source, result.text, result.inserted_lines).accepted


def test_file_without_final_newline_stays_without_it():
    source = "def a():\n    return 1"
    result = docs(source, FakeBackend([reply("Doc.")]))
    assert result.text == 'def a():\n    """Doc."""\n    return 1'


def test_non_ascii_text_survives():
    source = 'def a():\n    return "caffè"\n'
    result = docs(source, FakeBackend([reply("Restituisce il caffè.")]))
    assert 'return "caffè"' in result.text and "Restituisce il caffè." in result.text


# --- Files and the command -------------------------------------------------


def run(path, write, backend=None):
    out = io.StringIO()
    status = comment_command(
        [path], backend or FakeBackend([reply("Doc.")]), write, mode="docstrings", out=out
    )
    return status, out.getvalue()


def test_dry_run_shows_a_diff_and_writes_nothing(tmp_path):
    path = tmp_path / "mod.py"
    path.write_bytes(SOURCE.encode())
    status, output = run(path, write=False)
    assert status == 0
    assert path.read_bytes() == SOURCE.encode()
    assert '+    """Doc."""' in output and "dry run, nothing written" in output


def test_write_replaces_the_file_with_the_checked_text(tmp_path):
    path = tmp_path / "mod.py"
    path.write_bytes(SOURCE.encode())
    path.chmod(0o640)
    status, output = run(path, write=True)
    assert status == 0 and "written" in output
    assert docstrings(path.read_text())["add"] == "Doc."
    assert path.stat().st_mode & 0o777 == 0o640
    assert [p.name for p in tmp_path.iterdir()] == ["mod.py"]  # no temp file left behind


def test_write_with_nothing_to_add_leaves_the_file_alone(tmp_path):
    path = tmp_path / "mod.py"
    source = 'def a():\n    """Mine."""\n'
    path.write_bytes(source.encode())
    before = path.stat().st_mtime_ns
    assert run(path, write=True)[0] == 0
    assert path.read_bytes() == source.encode() and path.stat().st_mtime_ns == before


def test_unreadable_and_non_utf8_files_are_reported(tmp_path, capsys):
    bad = tmp_path / "latin.py"
    bad.write_bytes(b"x = '\xe9'\n")
    status = comment_command([bad, tmp_path / "missing.py"], FakeBackend(), write=True, mode="docstrings")
    assert status == 1
    assert bad.read_bytes() == b"x = '\xe9'\n"
    assert capsys.readouterr().err.count("cannot read") == 2


def test_write_is_atomic_when_writing_fails(tmp_path, monkeypatch):
    path = tmp_path / "mod.py"
    path.write_text("old\n")

    def boom(*args):
        raise OSError("disk full")

    monkeypatch.setattr(clio.os, "replace", boom)
    with pytest.raises(OSError):
        clio.write_text_atomic(path, "new\n")
    assert path.read_text() == "old\n"
    assert [p.name for p in tmp_path.iterdir()] == ["mod.py"]


# === Slice 2: inline comments ================================================

RETRY = textwrap.dedent(
    """
    def retry(func, attempts=3):
        last = None
        for attempt in range(attempts):
            try:
                return func()
            except OSError as error:
                last = error
        raise last
    """
).lstrip("\n")


def comments(source, backend):
    return clio.comment_source(source, backend, mode="comments")


def comment_reply(*pairs: str) -> str:
    return "COMMENTS:\n" + "\n".join(pairs)


# --- Reply parsing and layout ----------------------------------------------


def test_parse_comments_reads_numbered_lines():
    reply = "COMMENTS:\nS3: Keep the last error.\nS5) # Retry only on OSError.\nS7 - Stop here"
    assert clio.parse_comments(reply) == [
        (3, "Keep the last error."),
        (5, "Retry only on OSError."),
        (7, "Stop here"),
    ]


@pytest.mark.parametrize("reply", ["COMMENTS: NONE", "COMMENTS:\nNONE", "COMMENTS:\n"])
def test_parse_comments_accepts_none(reply):
    assert clio.parse_comments(reply) == []


def test_parse_comments_drops_code_the_model_repeated():
    reply = "COMMENTS:\nS2: Why.\n\nCode:\n```python\nS1 | x = 1\n```"
    assert clio.parse_comments(reply) == [(2, "Why.")]


def test_parse_comments_ignores_reasoning_and_wrapping_fence():
    assert clio.parse_comments("<think>x</think>```\nCOMMENTS:\nS1: Why.\n```") == [(1, "Why.")]


@pytest.mark.parametrize("bad", ["S1: Why.", "", "COMMENTS:\nThese are my thoughts."])
def test_parse_comments_rejects_unusable_replies(bad):
    with pytest.raises(ClioError):
        clio.parse_comments(bad)


def test_format_comment_wraps_and_indents():
    assert clio.format_comment("Short.", "    ", "\r\n") == ["    # Short.\r\n"]
    lines = clio.format_comment("word " * 40, "        ", "\n")
    assert len(lines) > 1 and all(len(line.rstrip()) <= 79 for line in lines)
    assert all(line.startswith("        # ") for line in lines)


# --- What the model is shown -----------------------------------------------


def test_numbered_code_marks_only_statements_that_can_take_a_comment():
    source = textwrap.dedent(
        '''
        def pick(x):
            """Doc."""
            if x > 1:
                y = 1  # trailing note
            elif x > 0:
                y = 2
            else:
                y = 3
            # a person's note
            a = 1; b = 2
            return y
        '''
    ).lstrip("\n")
    backend = FakeBackend(["COMMENTS: NONE"])
    comments(source, backend)
    shown = backend.prompts[0].split("Code:\n", 1)[1].splitlines()
    # Each row is a 5-character label column, then "| ", then the code.
    labels = {row[7:].strip(): row[:5].strip() for row in shown}
    assert labels['"""Doc."""'] == ""  # the docstring
    assert labels["if x > 1:"] == "S1"
    assert labels["y = 1  # trailing note"] == ""  # already commented
    assert labels["elif x > 0:"] == ""  # a branch, not a place for a comment
    assert labels["y = 2"] == "S2"
    assert labels["y = 3"] == "S3"
    assert labels["# a person's note"] == ""
    assert labels["a = 1; b = 2"] == ""  # the line above is a comment
    assert labels["return y"] == "S4"


# --- Inserting comments ----------------------------------------------------


def test_comment_goes_directly_above_the_named_statement_with_its_indent():
    result = comments(RETRY, FakeBackend([comment_reply("S5: Keep the last error to re-raise it.")]))
    assert statuses(result) == {"retry S5": ADDED}
    lines = result.text.splitlines()
    at = lines.index("            last = error")
    assert lines[at - 1] == "            # Keep the last error to re-raise it."
    assert argus.compare_code(RETRY, result.text).accepted
    assert argus.check_inserted_lines(RETRY, result.text, result.inserted_lines).accepted


def test_several_comments_in_one_function():
    result = comments(RETRY, FakeBackend([comment_reply("S1: First.", "S4: Second.", "S6: Third.")]))
    assert set(statuses(result).values()) == {ADDED} and len(result.outcomes) == 3
    assert [line.strip() for line in result.text.splitlines() if "#" in line] == [
        "# First.",
        "# Second.",
        "# Third.",
    ]
    assert argus.check_inserted_lines(RETRY, result.text, result.inserted_lines).accepted


def test_unknown_duplicate_and_empty_entries_are_rejected_and_the_rest_kept():
    reply = comment_reply("S9: Nowhere.", "S2: Fine.", "S2: Again.", "S3: #")
    result = comments(RETRY, FakeBackend([reply]))
    # S2 appears twice: the first mention is added, the second is rejected.
    assert sorted((o.name, o.status, o.reason) for o in result.outcomes) == [
        ("retry S2", ADDED, "added"),
        ("retry S2", REJECTED, "the statement was named twice"),
        ("retry S3", REJECTED, "the comment is empty"),
        ("retry S9", REJECTED, "not a numbered statement"),
    ]
    assert result.text.count("# Fine.") == 1 and "# Again." not in result.text


def test_model_proposing_nothing_leaves_the_file_alone():
    result = comments(RETRY, FakeBackend(["COMMENTS: NONE"]))
    assert result.text == RETRY and not result.changed
    assert statuses(result) == {"retry comments": SKIPPED}


def test_short_function_is_not_offered_to_the_model():
    backend = FakeBackend(["COMMENTS: NONE"])
    result = comments("def one():\n    return 1\n", backend)
    assert backend.prompts == [] and statuses(result) == {"one comments": SKIPPED}


def test_statement_with_an_existing_comment_cannot_be_targeted():
    source = RETRY.replace("    last = None\n", "    # set up\n    last = None\n")
    result = comments(source, FakeBackend([comment_reply("S1: Mine.")]))
    # S1 is now `for`, because `last = None` already has a person's comment.
    lines = result.text.splitlines()
    assert lines[lines.index("    last = None") - 1] == "    # set up"
    assert "    # Mine." in lines
    assert lines.index("    # Mine.") == lines.index("    for attempt in range(attempts):") - 1


def test_bad_reply_is_reported_without_touching_the_file():
    result = comments(RETRY, FakeBackend(["S1: no marker here"]))
    assert result.text == RETRY
    assert statuses(result) == {"retry comments": REJECTED}


def test_methods_get_comments_with_their_class_in_the_name():
    source = (
        "class Box:\n"
        "    def grow(self, n):\n"
        "        total = 0\n"
        "        for _ in range(n):\n"
        "            total += 1\n"
        "        return total\n"
    )
    backend = FakeBackend([comment_reply("S2: Counted by hand so each step can be traced.")])
    result = comments(source, backend)
    assert statuses(result) == {"Box.grow S2": ADDED}
    assert "This method belongs to the class Box." in backend.prompts[0]
    assert "        # Counted by hand so each step can be traced.\n        for _ in range(n):" in result.text


def test_crlf_file_keeps_its_line_endings_for_comments():
    source = RETRY.replace("\n", "\r\n")
    result = comments(source, FakeBackend([comment_reply("S1: Start empty.")]))
    assert result.changed and "\n" not in result.text.replace("\r\n", "")
    assert argus.check_inserted_lines(source, result.text, result.inserted_lines).accepted


def test_comment_that_is_not_directly_above_its_statement_is_dropped(monkeypatch):
    monkeypatch.setattr(clio, "_sits_above", lambda *args: False)
    result = comments(RETRY, FakeBackend([comment_reply("S1: Why.")]))
    assert result.text == RETRY and statuses(result) == {"retry S1": REJECTED}


# --- Both at once ----------------------------------------------------------


def test_docstring_stays_above_a_comment_on_the_first_statement():
    backend = FakeBackend([reply("Run it."), comment_reply("S1: Start empty.")])
    result = clio.comment_source(RETRY, backend)
    assert statuses(result) == {"retry": ADDED, "retry S1": ADDED}
    lines = result.text.splitlines()
    assert lines[1:3] == ['    """Run it."""', "    # Start empty."]
    assert lines[3] == "    last = None"
    assert argus.compare_code(RETRY, result.text).accepted
    assert argus.check_inserted_lines(RETRY, result.text, result.inserted_lines).accepted
    assert "DOCSTRING" in backend.prompts[0] and "COMMENTS" in backend.prompts[1]


def test_modes_ask_only_for_what_they_name():
    only_docs = FakeBackend([reply("Doc.")])
    clio.comment_source(RETRY, only_docs, mode="docstrings")
    assert len(only_docs.prompts) == 1 and "DOCSTRING" in only_docs.prompts[0]
    only_comments = FakeBackend(["COMMENTS: NONE"])
    clio.comment_source(RETRY, only_comments, mode="comments")
    assert len(only_comments.prompts) == 1 and "COMMENTS" in only_comments.prompts[0]
    with pytest.raises(ValueError):
        clio.comment_source(RETRY, FakeBackend(), mode="everything")


def test_command_mode_option_is_parsed_and_used(tmp_path):
    from momus.cli import build_parser

    assert build_parser().parse_args(["comment", "f.py"]).mode == "both"
    assert build_parser().parse_args(["comment", "f.py", "--mode", "comments"]).mode == "comments"
    path = tmp_path / "mod.py"
    path.write_text(RETRY)
    out = io.StringIO()
    backend = FakeBackend([comment_reply("S1: Why.")])
    assert comment_command([path], backend, False, mode="comments", out=out) == 0
    assert "+    # Why." in out.getvalue() and len(backend.prompts) == 1


# --- Outcomes say what they are and why they failed (used by the benchmark) --


def test_rejected_outcomes_carry_a_kind_and_a_cause(monkeypatch):
    class Down:
        def complete(self, prompt):
            raise BackendError("down")

    backend_failure = docs("def a():\n    pass\n", Down()).outcomes[0]
    assert (backend_failure.kind, backend_failure.cause) == ("docstring", "backend")

    bad_reply = docs("def a():\n    pass\n", FakeBackend(["junk"])).outcomes[0]
    assert (bad_reply.kind, bad_reply.cause) == ("docstring", "reply")

    unknown = comments(RETRY, FakeBackend([comment_reply("S9: Nowhere.")])).outcomes[0]
    assert (unknown.kind, unknown.cause) == ("comment", "anchor")

    monkeypatch.setattr(clio, "_sits_above", lambda *args: False)
    guard = comments(RETRY, FakeBackend([comment_reply("S1: Why.")])).outcomes[0]
    assert (guard.kind, guard.cause) == ("comment", "guard")

    added = clio.comment_source("def a():\n    pass\n", FakeBackend([reply("Doc.")]), "docstrings")
    assert (added.outcomes[0].status, added.outcomes[0].kind) == (ADDED, "docstring")


# --- Tidier docstrings and a firm limit on comments --------------------------


def test_section_entries_are_indented_and_headings_get_a_blank_line_before():
    text = parse_reply("DOCSTRING:\nDo it.\nArgs:\nfunc: What to call.\nn: How often.\nReturns:\nThe value.")
    assert text == "Do it.\n\nArgs:\n    func: What to call.\n    n: How often.\n\nReturns:\n    The value."


def test_text_that_is_already_tidy_or_has_no_sections_is_left_alone():
    tidy = "Do it.\n\nArgs:\n    func: What to call.\n\nReturns:\n    The value."
    assert parse_reply(f"DOCSTRING:\n{tidy}") == tidy
    plain = "Do it.\n\nIt has a note: take care.\nReturns: the value."  # not on a line of its own
    assert parse_reply(f"DOCSTRING:\n{plain}") == plain


def test_long_docstring_lines_are_wrapped_and_the_text_survives():
    words = "Retries a call with exponential backoff and gives up after a few attempts " * 3
    block = clio.format_docstring(words.strip(), "    ", "\n")
    assert len(block) > 3 and all(len(line.rstrip()) <= clio.DOCSTRING_WIDTH for line in block)
    assert block[0].startswith('    """') and block[-1] == '    """\n'
    inserted = f"def f():\n{''.join(block)}    return 1\n"
    assert " ".join(ast.get_docstring(ast.parse(inserted).body[0]).split()) == " ".join(words.split())


def test_wrapped_entries_keep_a_deeper_indent_for_the_continuation():
    text = parse_reply(
        "DOCSTRING:\nArgs:\nfunc: The function to retry, which is called with no arguments and may raise any "
        "exception at all, including ones nobody expected."
    )
    block = clio.format_docstring(text, "    ", "\n")
    assert block[1].startswith("        func: ") and block[2].startswith("            ")
    assert all(len(line.rstrip()) <= clio.DOCSTRING_WIDTH for line in block)


def test_a_single_line_that_needs_wrapping_becomes_a_multiline_docstring():
    block = clio.format_docstring("word " * 30, "", "\n")
    assert block[0].startswith('"""word') and block[-1] == '"""\n' and len(block) > 2


def test_no_more_than_three_comments_are_taken_for_one_function():
    reply = comment_reply("S1: One.", "S2: Two.", "S3: Three.", "S4: Four.", "S5: Five.")
    result = comments(RETRY, FakeBackend([reply]))
    by_name = {o.name: o for o in result.outcomes}
    assert [by_name[f"retry S{n}"].status for n in range(1, 6)] == [ADDED] * 3 + [REJECTED] * 2
    assert by_name["retry S4"].cause == "limit"
    assert result.text.count("# Four.") == 0 and result.text.count("# Three.") == 1


def test_comments_that_were_refused_do_not_use_up_the_limit():
    reply = comment_reply("S9: Nowhere.", "S1: One.", "S2: Two.", "S3: Three.")
    result = comments(RETRY, FakeBackend([reply]))
    assert sum(o.status == ADDED for o in result.outcomes) == 3
