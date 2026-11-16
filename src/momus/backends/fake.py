# A backend that never touches a model, for tests.

from collections.abc import Iterable


# Returns canned replies in order and records every prompt it receives.
#
# Once the canned replies run out, the last one is repeated, so a test never
# hangs or crashes on an extra call.
class FakeBackend:
    def __init__(self, replies: Iterable[str] = ("",)) -> None:
        self._replies = list(replies) or [""]
        self.prompts: list[str] = []

    # Record `prompt` and return the next canned reply.
    def complete(self, prompt: str) -> str:
        index = min(len(self.prompts), len(self._replies) - 1)
        self.prompts.append(prompt)
        return self._replies[index]
