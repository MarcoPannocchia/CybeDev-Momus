# Backend that asks Claude through Claude Code in non-interactive mode.
#
# It runs `claude -p` once per prompt. It needs no API key and no extra Python
# dependency: it uses whatever login the `claude` command already has, so the
# calls count against that account.
#
# By default `claude -p` loads everything an interactive session would: its
# long system prompt, every connected tool server, every skill. Measured on the
# maintainer's machine (2026-11-14), that was about 186 000 input tokens for a
# request whose own text was one line. The reviewer only reads text, so all of
# it is switched off here, which brought the same request down to about 1 300
# tokens. The command is also started from an empty folder, so the instructions
# of whatever project Momus runs in are not loaded either.

import json
import subprocess
import tempfile

from momus.backends import BackendError

# Replaces Claude Code's own system prompt, which is written for an agent with
# tools and is thousands of tokens long.
SYSTEM_PROMPT = "You review code comments. Follow the instructions in the message exactly."

# Everything that makes a request bigger without helping a text-only review.
LEAN_FLAGS = [
    "--tools", "",  # no built-in tools
    "--strict-mcp-config",  # no tool servers: none are passed, so none load
    "--disable-slash-commands",  # no skills or commands
    "--no-session-persistence",  # nothing saved to disk
    "--system-prompt", SYSTEM_PROMPT,
    "--output-format", "json",  # the reply plus the token counts
]  # fmt: skip


# Sends prompts to `claude -p` and returns the text of the reply.
class ClaudeCodeBackend:
    def __init__(
        self,
        model: str | None = None,
        command: str = "claude",
        timeout: float = 300.0,
        runner=subprocess.run,
    ) -> None:
        self.model = model
        self.command = command
        self.timeout = timeout
        # Injected so tests never start a real process.
        self._runner = runner
        # Token counts of the last reply as Claude Code reported them (or None).
        # ``prompt_tokens`` includes tokens written to or read from the cache.
        self.last_usage: dict | None = None

    # Send `prompt` on standard input and return the reply text.
    #
    # Raises:
    #     BackendError: if the command is missing, fails, times out, reports
    #         an error, or returns no text.
    def complete(self, prompt: str) -> str:
        args = [self.command, "-p", *LEAN_FLAGS]
        if self.model:
            args += ["--model", self.model]
        with tempfile.TemporaryDirectory(prefix="momus-review-") as neutral_folder:
            try:
                done = self._runner(
                    args,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    cwd=neutral_folder,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise BackendError(f"command not found: {self.command}") from exc
            except subprocess.TimeoutExpired as exc:
                raise BackendError(f"{self.command} did not answer within {self.timeout} s") from exc
            except OSError as exc:
                raise BackendError(f"cannot run {self.command}: {exc}") from exc
        if done.returncode != 0:
            detail = (done.stderr or done.stdout or "").strip()[:300]
            try:
                # On an API error the reason is in the JSON, far past 300 characters.
                body = json.loads(done.stdout)
                if body["is_error"]:
                    detail = str(body["result"])[:300]
            except (ValueError, KeyError, TypeError):
                pass
            raise BackendError(f"{self.command} exited with status {done.returncode}: {detail}")
        try:
            body = json.loads(done.stdout or "")
        except json.JSONDecodeError as exc:
            raise BackendError(f"{self.command} did not return JSON: {exc}") from exc
        if not isinstance(body, dict):
            raise BackendError(f"{self.command} returned an unexpected reply")
        if body.get("is_error"):
            raise BackendError(f"{self.command} reported an error: {str(body.get('result'))[:300]}")

        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        self.last_usage = {
            "prompt_tokens": sum(
                usage.get(key) or 0
                for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
            ),
            "completion_tokens": usage.get("output_tokens") or 0,
            "cost_usd": body.get("total_cost_usd"),
        }
        reply = body.get("result")
        if not isinstance(reply, str) or not reply.strip():
            raise BackendError(f"{self.command} returned no text")
        return reply.strip()
