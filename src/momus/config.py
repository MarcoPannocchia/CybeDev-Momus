"""Reads ``momus.toml`` and builds the configured backend.

The file holds settings only. API keys never go here: they live in
environment variables.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from momus.backends import Backend, BackendError
from momus.backends.local import LocalBackend

DEFAULT_CONFIG_NAME = "momus.toml"


@dataclass(frozen=True)
class LocalSettings:
    """Settings of the local model server."""

    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5-coder:1.5b"
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout: float = 600.0


def load_local_settings(path: Path | str = DEFAULT_CONFIG_NAME) -> LocalSettings:
    """Read the ``[local]`` table of ``path``; a missing file gives the defaults.

    Raises:
        BackendError: if the file is not valid TOML or has an unknown key.
    """
    config_path = Path(path)
    if not config_path.exists():
        return LocalSettings()
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise BackendError(f"{config_path} is not valid TOML: {exc}") from exc

    table = data.get("local", {})
    unknown = set(table) - set(LocalSettings.__dataclass_fields__)
    if unknown:
        raise BackendError(f"unknown key(s) in [local]: {', '.join(sorted(unknown))}")
    return LocalSettings(**table)


def build_local_backend(settings: LocalSettings) -> Backend:
    """Create a ``LocalBackend`` from ``settings``."""
    return LocalBackend(
        base_url=settings.base_url,
        model=settings.model,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        timeout=settings.timeout,
    )
