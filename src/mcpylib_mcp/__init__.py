"""MCP server that exposes a Minecraft server (via MCPyLib) to AI agents."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mcpylib-mcp")
except PackageNotFoundError:  # pragma: no cover - only when running from a raw source tree
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
