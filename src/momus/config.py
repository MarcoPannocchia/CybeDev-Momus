# Reads `momus.toml` and builds the configured backends.
#
# The file holds settings only. API keys never go here: they live in
# environment variables, and the file only names which variable to read.

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from momus.backends import Backend, BackendError
from momus.backends.anthropic import AnthropicBackend
from momus.backends.claude_code import ClaudeCodeBackend
from momus.backends.local import LocalBackend

DEFAULT_CONFIG_NAME = "momus.toml"
REVIEW_BACKENDS = ("claude_code", "anthropic")


# Settings of the local model server.
@dataclass(frozen=True)
class LocalSettings:
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5-coder:1.5b"
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout: float = 600.0


# Settings of the review stage (the strong model).
@dataclass(frozen=True)
class ReviewSettings:
    backend: str = "claude_code"
    # The model for long files, and for every file if ``small_model`` is empty.
    # Empty means the backend's own default (Claude Code only), which can be
    # the most expensive model of the account. Claude Code accepts aliases
    # such as "sonnet"; the Anthropic API needs full model names.
    model: str = "sonnet"
    # A cheaper model for short files. Empty turns the routing off.
    small_model: str = "haiku"
    # A file with at most this many lines is short. The value is a first
    # guess, not a measured threshold.
    small_file_lines: int = 200
    api_key_env: str = "ANTHROPIC_API_KEY"
    max_tokens: int = 1024
    timeout: float = 300.0
    # Comments sent to the reviewer in one request.
    max_items: int = 10


# Read one table of the config file into `settings_class`.
#
# A missing file or table gives the defaults.
#
# Raises:
#     BackendError: if the file is not valid TOML or the table has an
#         unknown key.
def _read_table(path: Path | str, table: str, settings_class):
    config_path = Path(path)
    if not config_path.exists():
        return settings_class()
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise BackendError(f"{config_path} is not valid TOML: {exc}") from exc

    values = data.get(table, {})
    unknown = set(values) - {f.name for f in fields(settings_class)}
    if unknown:
        raise BackendError(f"unknown key(s) in [{table}]: {', '.join(sorted(unknown))}")
    return settings_class(**values)


# Read the `[local]` table of `path`; a missing file gives the defaults.
def load_local_settings(path: Path | str = DEFAULT_CONFIG_NAME) -> LocalSettings:
    return _read_table(path, "local", LocalSettings)


# Read the `[review]` table of `path`; a missing file gives the defaults.
#
# Raises:
#     BackendError: if the backend name is not one of `REVIEW_BACKENDS`, in
#         addition to the errors of reading the file.
def load_review_settings(path: Path | str = DEFAULT_CONFIG_NAME) -> ReviewSettings:
    settings = _read_table(path, "review", ReviewSettings)
    if settings.backend not in REVIEW_BACKENDS:
        raise BackendError(f"[review] backend must be one of {REVIEW_BACKENDS}, got {settings.backend!r}")
    return settings


# Create a `LocalBackend` from `settings`.
def build_local_backend(settings: LocalSettings) -> Backend:
    return LocalBackend(
        base_url=settings.base_url,
        model=settings.model,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        timeout=settings.timeout,
    )


def _review_backend(settings: ReviewSettings, model: str) -> Backend:
    if settings.backend == "claude_code":
        return ClaudeCodeBackend(model=model or None, timeout=settings.timeout)
    if not model:
        raise BackendError("[review] model is required for the anthropic backend")
    return AnthropicBackend(
        model=model,
        api_key_env=settings.api_key_env,
        max_tokens=settings.max_tokens,
        timeout=settings.timeout,
    )


# Create the main review backend named in `settings`.
#
# Raises:
#     BackendError: if the Anthropic backend is chosen without a model.
def build_review_backend(settings: ReviewSettings) -> Backend:
    return _review_backend(settings, settings.model)


# Create the backend for short files, or None if routing is off.
#
# Routing is off when `small_model` is empty or the same as `model`.
def build_small_review_backend(settings: ReviewSettings) -> Backend | None:
    if not settings.small_model or settings.small_model == settings.model:
        return None
    return _review_backend(settings, settings.small_model)
