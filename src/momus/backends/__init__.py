# Backends: interchangeable ways to send a prompt to a model and get text back.
#
# Every backend implements the same tiny interface, so no pipeline stage is tied
# to one model or vendor.

from typing import Protocol


# Raised when a backend cannot return a usable answer (server down, bad reply).
class BackendError(Exception):
    pass


# The one thing every backend must do: turn a prompt into text.
class Backend(Protocol):
    # Send `prompt` to the model and return its reply as plain text.
    #
    # Raises:
    #     BackendError: if no usable answer could be obtained.
    def complete(self, prompt: str) -> str:
        ...
