"""Runtime configuration: environment variables, overridable by command-line flags."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from typing import Any

from .errors import ConfigError

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
TRANSPORTS = ("stdio", "http")
_TRANSPORT_ALIASES = {"streamable-http": "http", "streamable_http": "http"}
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}

# Settings field -> environment variable.
ENV_VARS: dict[str, str] = {
    "host": "MCPYLIB_HOST",
    "port": "MCPYLIB_PORT",
    "token": "MCPYLIB_TOKEN",
    "timeout": "MCPYLIB_TIMEOUT",
    "max_blocks": "MCPYLIB_MAX_BLOCKS",
    "read_only": "MCPYLIB_READ_ONLY",
    "allowed_tools": "MCPYLIB_ALLOWED_TOOLS",
    "denied_tools": "MCPYLIB_DENIED_TOOLS",
    "transport": "MCPYLIB_TRANSPORT",
    "http_host": "MCPYLIB_HTTP_HOST",
    "http_port": "MCPYLIB_HTTP_PORT",
    "log_level": "MCPYLIB_LOG_LEVEL",
}


@dataclass(frozen=True)
class Settings:
    """Validated configuration for one server process.

    ``token`` is excluded from ``repr``/``str`` so it cannot leak into logs or tracebacks.
    """

    host: str = "localhost"
    port: int = 65535
    token: str = field(default="", repr=False)
    timeout: float = 30.0
    max_blocks: int = 100_000
    read_only: bool = False
    allowed_tools: tuple[str, ...] = ()
    denied_tools: tuple[str, ...] = ()
    transport: str = "stdio"
    http_host: str = "127.0.0.1"
    http_port: int = 8000
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ConfigError(f"host ({ENV_VARS['host']}) must not be empty")
        _check_port("port", self.port)
        _check_port("http_port", self.http_port)
        if not 0 < self.timeout <= 3600:
            raise ConfigError(f"timeout ({ENV_VARS['timeout']}) must be between 0 and 3600 seconds")
        if self.max_blocks < 1:
            raise ConfigError(f"max_blocks ({ENV_VARS['max_blocks']}) must be at least 1")
        if self.transport not in TRANSPORTS:
            raise ConfigError(f"transport ({ENV_VARS['transport']}) must be one of {', '.join(TRANSPORTS)}")
        if self.log_level not in LOG_LEVELS:
            raise ConfigError(f"log_level ({ENV_VARS['log_level']}) must be one of {', '.join(LOG_LEVELS)}")

    def __repr__(self) -> str:
        parts = [f"{f.name}={getattr(self, f.name)!r}" for f in fields(self) if f.name != "token"]
        parts.insert(2, "token=" + ("'***'" if self.token else "''"))
        return f"Settings({', '.join(parts)})"

    __str__ = __repr__

    @property
    def target(self) -> str:
        """``host:port`` of the MCPyLib plugin, for messages."""
        return f"{self.host}:{self.port}"


def _check_port(name: str, value: int) -> None:
    if not 1 <= value <= 65535:
        raise ConfigError(f"{name} ({ENV_VARS[name]}) must be between 1 and 65535")


def parse_list(value: str) -> tuple[str, ...]:
    """Split a comma- and/or whitespace-separated list, dropping empty items."""
    return tuple(item for item in re.split(r"[,\s]+", value) if item)


def _parse(name: str, raw: str) -> Any:
    """Convert one environment variable value to the type of Settings field ``name``."""
    env = ENV_VARS[name]
    text = raw.strip()
    try:
        if name in ("port", "http_port", "max_blocks"):
            return int(text)
        if name == "timeout":
            return float(text)
    except ValueError:
        raise ConfigError(f"{env} must be a number (got {raw!r})") from None
    if name == "read_only":
        lowered = text.lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        raise ConfigError(f"{env} must be true or false (got {raw!r})")
    if name in ("allowed_tools", "denied_tools"):
        return parse_list(text)
    if name == "transport":
        return _TRANSPORT_ALIASES.get(text.lower(), text.lower())
    if name == "log_level":
        return text.upper()
    return text


def load_settings(
    environ: Mapping[str, str],
    overrides: Mapping[str, Any] | None = None,
    *,
    require_token: bool = True,
) -> Settings:
    """Build :class:`Settings` from environment variables plus explicit overrides.

    ``overrides`` (typically parsed command-line flags) win over the environment; a value of
    ``None`` means "not given". Validation errors name the environment variable involved.
    """
    values: dict[str, Any] = {}
    for name, env in ENV_VARS.items():
        if env in environ:
            values[name] = _parse(name, environ[env])
    for name, value in (overrides or {}).items():
        if value is None:
            continue
        if name not in ENV_VARS:
            raise ConfigError(f"unknown setting: {name}")
        if name == "transport":
            value = _TRANSPORT_ALIASES.get(value, value)
        elif name == "log_level":
            value = str(value).upper()
        elif name in ("allowed_tools", "denied_tools") and isinstance(value, str):
            value = parse_list(value)
        values[name] = value

    if isinstance(values.get("token"), str):
        values["token"] = values["token"].strip()
    if require_token and not values.get("token"):
        raise ConfigError(
            "no MCPyLib token configured. Run '/mcpylib token' on the Minecraft server and put the "
            "value in the MCPYLIB_TOKEN environment variable."
        )

    try:
        return Settings(**values)
    except ConfigError as exc:
        # Re-raise with the environment variable name first, which is what users can act on.
        raise ConfigError(_mention_env(str(exc))) from None


def _mention_env(message: str) -> str:
    for name, env in ENV_VARS.items():
        if message.startswith(f"{name} ("):
            return f"{env}: {message}"
    return message
