"""Backend for Claude through the Anthropic Messages API.

Plain HTTP from the standard library, like the local backend: one JSON request
needs no SDK, so no extra dependency. The API key is read from an environment
variable, never from code or from ``momus.toml``.
"""

import json
import os
import urllib.error
import urllib.request

from momus.backends import BackendError

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicBackend:
    """Sends prompts to the Messages API and returns the text of the reply."""

    def __init__(
        self,
        model: str,
        api_key_env: str = "ANTHROPIC_API_KEY",
        max_tokens: int = 1024,
        timeout: float = 120.0,
        url: str = API_URL,
    ) -> None:
        self.model = model
        self.api_key_env = api_key_env
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.url = url

    def complete(self, prompt: str) -> str:
        """Send ``prompt`` as one user message and return the reply text.

        Raises:
            BackendError: if the key is not set, the server cannot be reached,
                answers with an error, or returns an unexpected shape.
        """
        key = os.environ.get(self.api_key_env)
        if not key:
            raise BackendError(f"environment variable {self.api_key_env} is not set")
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": key,
                "anthropic-version": API_VERSION,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.load(response)
        except urllib.error.HTTPError as exc:
            # Read the error text, which never contains the key.
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise BackendError(f"server returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BackendError(f"cannot reach {self.url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise BackendError(f"server reply is not valid JSON: {exc}") from exc

        try:
            parts = [block["text"] for block in body["content"] if block.get("type") == "text"]
        except (KeyError, TypeError) as exc:
            raise BackendError("server reply has no content blocks") from exc
        if not parts:
            raise BackendError("server reply has no text")
        return "".join(parts)
