"""Small helpers shared by the MCP-level tests."""

from contextlib import asynccontextmanager
from typing import Any

from mcp import Client

from mcpylib_mcp.bridge import MinecraftBridge
from mcpylib_mcp.config import Settings
from mcpylib_mcp.server import create_server


def make_settings(fake, **overrides: Any) -> Settings:
    options: dict[str, Any] = {"host": "127.0.0.1", "port": fake.port, "token": fake.token, "timeout": 2.0}
    return Settings(**(options | overrides))


@asynccontextmanager
async def connect(fake, **overrides: Any):
    """An in-process MCP client talking to a freshly built server wired to ``fake``."""
    settings = make_settings(fake, **overrides)
    bridge = MinecraftBridge.from_settings(settings)
    server = create_server(settings, bridge=bridge)
    try:
        async with Client(server, cache=None) as client:
            yield client
    finally:
        bridge.close()


def ok_data(result) -> dict[str, Any]:
    """Structured content of a successful tool result."""
    assert not result.is_error, result.content[0].text
    assert result.structured_content is not None
    return result.structured_content


def error_text(result) -> str:
    """Text of a failed tool result."""
    assert result.is_error, f"expected an error, got {result.structured_content}"
    return result.content[0].text
