"""Reads ``momus.toml`` and builds the configured backends.

The file holds settings only. API keys never go here: they live in
environment variables, and the file only names which variable to read.
"""

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from momus.backends import Backend, BackendError
from momus.backends.anthropic import AnthropicBackend
from momus.backends.claude_code import ClaudeCodeBackend
from momus.backends.local import LocalBackend

DEFAULT_CONFIG_NAME = "momus.toml"
REVIEW_BACKENDS = ("claude_code", "anthropic")


@dataclass(frozen=True)
class LocalSettings:
    """Settings of the local model server."""

    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5-coder:1.5b"
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout: float = 600.0


@dataclass(frozen=True)
class ReviewSettings:
    """Settings of the review stage (the strong model)."""

    backend: str = "claude_code"
    # Empty means "the backend's own default" for Claude Code; the Anthropic API
    # needs a model name.
    model: str = ""
    api_key_env: str = "ANTHROPIC_API_KEY"
    max_tokens: int = 1024
    timeout: float = 300.0
    # Comments sent to the reviewer in one request.
    max_items: int = 10


def _read_table(path: Path | str, table: str, settings_class):
    """Read one table of the config file into ``settings_class``.

    A missing file or table gives the defaults.

    Raises:
        BackendError: if the file is not valid TOML or the table has an
            unknown key.
    """
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


def load_local_settings(path: Path | str = DEFAULT_CONFIG_NAME) -> LocalSettings:
    """Read the ``[local]`` table of ``path``; a missing file gives the defaults."""
    return _read_table(path, "local", LocalSettings)


def load_review_settings(path: Path | str = DEFAULT_CONFIG_NAME) -> ReviewSettings:
    """Read the ``[review]`` table of ``path``; a missing file gives the defaults.

    Raises:
        BackendError: if the backend name is not one of ``REVIEW_BACKENDS``, in
            addition to the errors of reading the file.
    """
    settings = _read_table(path, "review", ReviewSettings)
    if settings.backend not in REVIEW_BACKENDS:
        raise BackendError(f"[review] backend must be one of {REVIEW_BACKENDS}, got {settings.backend!r}")
    return settings


def build_local_backend(settings: LocalSettings) -> Backend:
    """Create a ``LocalBackend`` from ``settings``."""
    return LocalBackend(
        base_url=settings.base_url,
        model=settings.model,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        timeout=settings.timeout,
    )


def build_review_backend(settings: ReviewSettings) -> Backend:
    """Create the review backend named in ``settings``.

    Raises:
        BackendError: if the Anthropic backend is chosen without a model.
    """
    if settings.backend == "claude_code":
        return ClaudeCodeBackend(model=settings.model or None, timeout=settings.timeout)
    if not settings.model:
        raise BackendError("[review] model is required for the anthropic backend")
    return AnthropicBackend(
        model=settings.model,
        api_key_env=settings.api_key_env,
        max_tokens=settings.max_tokens,
        timeout=settings.timeout,
    )
