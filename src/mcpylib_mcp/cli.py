"""Command-line entry point: ``mcpylib-mcp``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING

from . import __version__
from .config import LOG_LEVELS, Settings, load_settings
from .errors import ConfigError

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

logger = logging.getLogger("mcpylib_mcp")

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
_HANDLER_NAME = "mcpylib-mcp"
# argparse destination -> Settings field (every one of them is also an environment variable)
_SETTING_FLAGS = (
    "host",
    "port",
    "token",
    "timeout",
    "max_blocks",
    "read_only",
    "allowed_tools",
    "denied_tools",
    "transport",
    "http_host",
    "http_port",
    "log_level",
)

EPILOG = """\
environment variables (command-line flags take precedence):
  MCPYLIB_TOKEN          MCPyLib plugin token (required; run '/mcpylib token' in game)
  MCPYLIB_HOST           Minecraft server host                      (default: localhost)
  MCPYLIB_PORT           MCPyLib plugin port                        (default: 65535)
  MCPYLIB_TIMEOUT        seconds to wait for the plugin             (default: 30)
  MCPYLIB_MAX_BLOCKS     max blocks one tool call may read/change   (default: 100000)
  MCPYLIB_READ_ONLY      true = register only non-mutating tools    (default: false)
  MCPYLIB_ALLOWED_TOOLS  only these tools: names, globs (get_*), group:<name>
  MCPYLIB_DENIED_TOOLS   never these tools (same syntax; wins over the allowlist)
  MCPYLIB_TRANSPORT      stdio or http                              (default: stdio)
  MCPYLIB_HTTP_HOST      HTTP bind address                          (default: 127.0.0.1)
  MCPYLIB_HTTP_PORT      HTTP port                                  (default: 8000)
  MCPYLIB_LOG_LEVEL      DEBUG, INFO, WARNING, ERROR or CRITICAL    (default: INFO)

tool groups: server, blocks, players, world, entities, chat, scoreboard
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcpylib-mcp",
        description="MCP server that lets AI agents control a Minecraft server through MCPyLib.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    minecraft = parser.add_argument_group("Minecraft connection")
    minecraft.add_argument("--mc-host", dest="host", metavar="HOST", help="Minecraft server host (MCPYLIB_HOST)")
    minecraft.add_argument(
        "--mc-port", dest="port", type=int, metavar="PORT", help="MCPyLib plugin port (MCPYLIB_PORT)"
    )
    minecraft.add_argument(
        "--token",
        help="MCPyLib token. Prefer MCPYLIB_TOKEN: command lines are visible to other users of this computer.",
    )
    minecraft.add_argument("--timeout", type=float, metavar="SECONDS", help="Plugin response timeout (MCPYLIB_TIMEOUT)")

    safety = parser.add_argument_group("safety")
    safety.add_argument(
        "--max-blocks", type=int, metavar="N", help="Max blocks one call may read or change (MCPYLIB_MAX_BLOCKS)"
    )
    safety.add_argument(
        "--read-only",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Register only tools that do not change the world (MCPYLIB_READ_ONLY)",
    )
    safety.add_argument(
        "--allow-tools", dest="allowed_tools", metavar="LIST", help="Comma-separated allowlist (MCPYLIB_ALLOWED_TOOLS)"
    )
    safety.add_argument(
        "--deny-tools", dest="denied_tools", metavar="LIST", help="Comma-separated denylist (MCPYLIB_DENIED_TOOLS)"
    )

    transport = parser.add_argument_group("MCP transport")
    transport.add_argument(
        "--transport", choices=["stdio", "http", "streamable-http"], help="stdio (default) or streamable HTTP"
    )
    transport.add_argument(
        "--host", dest="http_host", metavar="HOST", help="HTTP bind address (MCPYLIB_HTTP_HOST, default 127.0.0.1)"
    )
    transport.add_argument(
        "--port", dest="http_port", type=int, metavar="PORT", help="HTTP port (MCPYLIB_HTTP_PORT, default 8000)"
    )

    other = parser.add_argument_group("other")
    other.add_argument("--log-level", type=str.upper, choices=LOG_LEVELS, help="Log level (MCPYLIB_LOG_LEVEL)")
    other.add_argument(
        "--list-tools", action="store_true", help="Print the tools these settings enable and exit (no token needed)"
    )
    return parser


def parse_settings(argv: Sequence[str] | None, environ: Mapping[str, str]) -> tuple[Settings, argparse.Namespace]:
    """Parse flags and merge them over the environment."""
    args = build_parser().parse_args(argv)
    overrides = {name: getattr(args, name) for name in _SETTING_FLAGS}
    return load_settings(environ, overrides, require_token=not args.list_tools), args


class RedactingFormatter(logging.Formatter):
    """Replaces secrets in every formatted record, including tracebacks."""

    def __init__(self, fmt: str, secrets: Iterable[str]) -> None:
        super().__init__(fmt)
        self._secrets = [secret for secret in secrets if secret]

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text


def configure_logging(level: str, secrets: Iterable[str]) -> None:
    """Log to stderr (stdout carries the stdio transport), never printing ``secrets``."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if handler.get_name() == _HANDLER_NAME:
            root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s", secrets))
    root.addHandler(handler)
    root.setLevel(level)


def format_tool_list(settings: Settings) -> str:
    """Human-readable list of all tools, marking those the settings enable."""
    from .bridge import MinecraftBridge
    from .server import build_registry, enabled_tool_names

    registry = build_registry(settings, MinecraftBridge.from_settings(settings))
    enabled = set(enabled_tool_names(settings, registry))
    lines = [
        f"mcpylib-mcp {__version__}: {len(enabled)} of {len(registry.specs)} tools enabled "
        f"(read-only: {'yes' if settings.read_only else 'no'}, max blocks per call: {settings.max_blocks:,})",
        "(+ enabled, - disabled)",
    ]
    group = None
    for spec in registry.specs:
        if spec.group != group:
            group = spec.group
            lines.append(f"\ngroup:{group}")
        access = "read-only" if spec.read_only else "destructive" if spec.destructive else "changes the world"
        lines.append(f"  {'+' if spec.name in enabled else '-'} {spec.name:<24} {access}")
    return "\n".join(lines)


def run(server: MCPServer, settings: Settings) -> None:
    logger.debug("Settings: %r", settings)
    if settings.transport == "http":
        if settings.http_host not in LOOPBACK_HOSTS:
            logger.warning(
                "Serving MCP over HTTP on %s:%d without authentication: anyone who can reach this port can "
                "control the Minecraft server. Bind to 127.0.0.1 or put an authenticating proxy in front.",
                settings.http_host,
                settings.http_port,
            )
        logger.info("Serving MCP over streamable HTTP at http://%s:%d/mcp", settings.http_host, settings.http_port)
        server.run("streamable-http", host=settings.http_host, port=settings.http_port)
    else:
        logger.info("Serving MCP over stdio; MCPyLib plugin at %s", settings.target)
        server.run("stdio")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        settings, args = parse_settings(argv, os.environ)
        if args.list_tools:
            print(format_tool_list(settings))
            return 0
        configure_logging(settings.log_level, [settings.token])
        from .server import create_server

        server = create_server(settings)
    except ConfigError as exc:
        print(f"mcpylib-mcp: error: {exc}", file=sys.stderr)
        return 2
    try:
        run(server, settings)
    except KeyboardInterrupt:
        pass
    return 0
