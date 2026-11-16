# Backend for a local model server that speaks the OpenAI chat format.
#
# Ollama, llama.cpp and LM Studio all expose `/v1/chat/completions`. Here that
# format is used only as a local transport protocol. Plain HTTP from the standard
# library is enough for one JSON request, so no extra dependency is needed.
#
# The context window is NOT set per request: the `/v1` endpoint has no portable
# way to do it. Configure it on the server instead (for Ollama, the
# `OLLAMA_CONTEXT_LENGTH` environment variable or a Modelfile).

import json
import urllib.error
import urllib.request

from momus.backends import BackendError


# Sends prompts to a local OpenAI-format server and returns the reply text.
class LocalBackend:
    def __init__(
        self,
        base_url: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout: float = 600.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        # Token counts of the last reply, as the server reported them (or None).
        self.last_usage: dict | None = None

    # Send `prompt` as one user message and return the model's reply.
    #
    # Raises:
    #     BackendError: if the server is unreachable, answers with an error,
    #         or returns a reply in an unexpected shape.
    def complete(self, prompt: str) -> str:
        payload: dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "stream": False,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.load(response)
        except urllib.error.HTTPError as exc:
            # The server answered, but with an error (unknown model, bad request).
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise BackendError(f"server returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BackendError(f"cannot reach {self.base_url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise BackendError(f"server reply is not valid JSON: {exc}") from exc

        self.last_usage = body.get("usage") if isinstance(body, dict) else None
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError("server reply has no choices[0].message.content") from exc
        if not isinstance(content, str):
            raise BackendError("reply content is not text")
        return content
