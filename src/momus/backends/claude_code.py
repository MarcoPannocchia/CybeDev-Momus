"""Backend that asks Claude through Claude Code in non-interactive mode.

It runs ``claude -p`` once per prompt. It needs no API key and no extra Python
dependency: it uses whatever login the ``claude`` command already has, so the
calls count against that account.

The command is started with every tool turned off (the reviewer only has to
read text), with no saved session, and from an empty folder so that the
instructions of whatever project Momus happens to be run in are not loaded
into every review.
"""

import subprocess
import tempfile

from momus.backends import BackendError


class ClaudeCodeBackend:
    """Sends prompts to ``claude -p`` and returns what it prints."""

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

    def complete(self, prompt: str) -> str:
        """Send ``prompt`` on standard input and return the reply text.

        Raises:
            BackendError: if the command is missing, fails, times out, or
                prints nothing.
        """
        args = [self.command, "-p", "--tools", "", "--no-session-persistence"]
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
            raise BackendError(f"{self.command} exited with status {done.returncode}: {detail}")
        reply = (done.stdout or "").strip()
        if not reply:
            raise BackendError(f"{self.command} printed nothing")
        return reply
