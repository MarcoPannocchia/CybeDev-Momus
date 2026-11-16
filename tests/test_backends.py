# Tests for the backend interface, the fake backend, the config and the local client.
#
# The local client is tested against a tiny stub HTTP server running on
# localhost, so no model is involved. Tests that need a real Ollama server are
# marked `integration` and are skipped by default.

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from momus.backends import BackendError
from momus.backends.fake import FakeBackend
from momus.backends.local import LocalBackend
from momus.config import LocalSettings, build_local_backend, load_local_settings


# A local HTTP server that returns one fixed response and records requests.
class StubServer:
    def __init__(self, status: int = 200, body: bytes = b"") -> None:
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                outer.requests.append(
                    {"path": self.path, "json": json.loads(self.rfile.read(length))}
                )
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()


def ok_reply(text: str) -> bytes:
    return json.dumps({"choices": [{"message": {"content": text}}]}).encode()


# --- FakeBackend -----------------------------------------------------------


def test_fake_backend_returns_replies_in_order_and_records_prompts():
    fake = FakeBackend(["one", "two"])
    assert fake.complete("a") == "one"
    assert fake.complete("b") == "two"
    assert fake.prompts == ["a", "b"]


def test_fake_backend_repeats_last_reply_when_exhausted():
    fake = FakeBackend(["only"])
    assert [fake.complete("x"), fake.complete("y")] == ["only", "only"]


# --- Config ----------------------------------------------------------------


def test_missing_config_file_gives_defaults(tmp_path):
    assert load_local_settings(tmp_path / "nope.toml") == LocalSettings()


def test_config_overrides_defaults(tmp_path):
    path = tmp_path / "momus.toml"
    path.write_text('[local]\nmodel = "other:1b"\ntemperature = 0.2\nmax_tokens = 64\n')
    settings = load_local_settings(path)
    assert (settings.model, settings.temperature, settings.max_tokens) == (
        "other:1b",
        0.2,
        64,
    )
    assert settings.base_url == LocalSettings().base_url


def test_config_unknown_key_is_rejected(tmp_path):
    path = tmp_path / "momus.toml"
    path.write_text("[local]\nnum_ctx = 8192\n")
    with pytest.raises(BackendError, match="num_ctx"):
        load_local_settings(path)


def test_config_invalid_toml_is_rejected(tmp_path):
    path = tmp_path / "momus.toml"
    path.write_text("[local\n")
    with pytest.raises(BackendError, match="not valid TOML"):
        load_local_settings(path)


def test_repo_example_config_loads():
    # The shipped momus.toml must stay valid (run from the repository root).
    assert load_local_settings("momus.toml").model


def test_build_local_backend_uses_settings():
    backend = build_local_backend(LocalSettings(model="m:1b", temperature=0.5))
    assert isinstance(backend, LocalBackend)
    assert (backend.model, backend.temperature) == ("m:1b", 0.5)


# --- LocalBackend ----------------------------------------------------------


def test_local_backend_sends_expected_request_and_returns_text():
    with StubServer(body=ok_reply("hello")) as server:
        backend = LocalBackend(server.base_url, "m:1b", temperature=0.0, max_tokens=32)
        assert backend.complete("say hi") == "hello"
    (request,) = server.requests
    assert request["path"] == "/v1/chat/completions"
    assert request["json"] == {
        "model": "m:1b",
        "messages": [{"role": "user", "content": "say hi"}],
        "temperature": 0.0,
        "stream": False,
        "max_tokens": 32,
    }


def test_local_backend_omits_max_tokens_when_unset():
    with StubServer(body=ok_reply("x")) as server:
        LocalBackend(server.base_url, "m").complete("p")
    assert "max_tokens" not in server.requests[0]["json"]


def test_local_backend_http_error_becomes_backend_error():
    with StubServer(status=404, body=b'{"error": "model not found"}') as server:
        with pytest.raises(BackendError, match="HTTP 404"):
            LocalBackend(server.base_url, "missing").complete("p")


@pytest.mark.parametrize(
    "body",
    [b"not json", b"{}", b'{"choices": []}', b'{"choices": [{"message": {"content": 5}}]}'],
)
def test_local_backend_bad_reply_becomes_backend_error(body):
    with StubServer(body=body) as server:
        with pytest.raises(BackendError):
            LocalBackend(server.base_url, "m").complete("p")


def test_local_backend_unreachable_server_becomes_backend_error():
    # Port 9 (discard) on localhost is closed; the connection must fail cleanly.
    with pytest.raises(BackendError, match="cannot reach"):
        LocalBackend("http://127.0.0.1:9/v1", "m", timeout=2).complete("p")


# --- Integration (real Ollama, skipped by default) -------------------------


def _ollama_models() -> list[str]:
    try:
        with urllib.request.urlopen("http://localhost:11434/v1/models", timeout=2) as r:
            return [m["id"] for m in json.load(r)["data"]]
    except OSError:
        return []


@pytest.mark.integration
def test_real_ollama_answers():
    model = load_local_settings("momus.toml").model
    if model not in _ollama_models():
        pytest.skip(f"Ollama is not running or {model} is not installed")
    backend = build_local_backend(load_local_settings("momus.toml"))
    assert backend.complete("Reply with the single word: ready").strip()


def test_local_backend_keeps_the_token_counts_the_server_reports():
    body = json.dumps(
        {
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        }
    ).encode()
    with StubServer(body=body) as server:
        backend = LocalBackend(server.base_url, "m")
        assert backend.last_usage is None
        backend.complete("p")
    assert backend.last_usage == {"prompt_tokens": 7, "completion_tokens": 3}


def test_local_backend_without_usage_in_the_reply_reports_none():
    with StubServer(body=ok_reply("hi")) as server:
        backend = LocalBackend(server.base_url, "m")
        backend.complete("p")
    assert backend.last_usage is None
