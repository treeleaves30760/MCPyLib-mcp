"""Assembles the MCP server: tools filtered by the safety settings, plus resources and prompts."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer

from . import __version__
from .bridge import MinecraftBridge
from .config import Settings
from .registry import ToolRegistry
from .safety import select_tools
from .tools import register_all

logger = logging.getLogger(__name__)

SERVER_NAME = "mcpylib-mcp"
HOMEPAGE = "https://github.com/treeleaves30760/MCPyLib-mcp"


def build_registry(settings: Settings, bridge: MinecraftBridge) -> ToolRegistry:
    """Every tool, before filtering."""
    registry = ToolRegistry(settings, bridge)
    register_all(registry)
    return registry


def enabled_tool_names(settings: Settings, registry: ToolRegistry) -> list[str]:
    """Tools allowed by read-only mode and the allow/deny lists (raises ConfigError on bad entries)."""
    return select_tools(
        [spec.info for spec in registry.specs],
        read_only=settings.read_only,
        allowed=settings.allowed_tools,
        denied=settings.denied_tools,
    )


def build_instructions(settings: Settings, enabled: list[str]) -> str:
    if settings.read_only:
        mode = (
            "This server is in read-only mode: only tools that inspect the world are available, "
            "so you cannot change anything."
        )
    else:
        mode = "Changes are immediate and cannot be undone: inspect with get_blocks before overwriting player builds."
    if "run_command" in enabled:
        mode += " run_command runs any console command; prefer the dedicated tools."
    return (
        "Controls a live Minecraft Java server (Paper/Spigot with the MCPyLib plugin).\n"
        "Conventions: +X is east, +Z is south, +Y is up (overworld build range Y -64 to 319). Block, world and "
        "particle tools act on the server's main world; player and entity tools act wherever that player or "
        "entity is. Ids are Minecraft names such as 'minecraft:stone' (the namespace is optional).\n"
        "Work efficiently: find positions with get_players/get_player_position, find the ground with "
        "get_height_map, build solid parts with fill_region and detailed parts with build_from_layers, and "
        "check the result with get_blocks.\n"
        f"Limits: each call may read or change at most {settings.max_blocks:,} blocks (MCPYLIB_MAX_BLOCKS); "
        f"split bigger jobs into several calls. {mode}"
    )


def create_server(settings: Settings, bridge: MinecraftBridge | None = None) -> MCPServer:
    """Build a ready-to-run MCP server for ``settings``.

    The bridge connects lazily, so the server starts even while Minecraft is offline; tool calls then
    fail with a clear connection error until it is reachable.
    """
    bridge = bridge or MinecraftBridge.from_settings(settings)
    registry = build_registry(settings, bridge)
    enabled = enabled_tool_names(settings, registry)

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[dict[str, Any]]:
        try:
            yield {}
        finally:
            bridge.close()

    server = MCPServer(
        SERVER_NAME,
        title="MCPyLib Minecraft",
        description="Control a Minecraft server (Paper/Spigot + MCPyLib plugin): blocks, players, entities and more.",
        instructions=build_instructions(settings, enabled),
        website_url=HOMEPAGE,
        version=__version__,
        tools=registry.build_tools(enabled),
        log_level=settings.log_level,  # type: ignore[arg-type]
        lifespan=lifespan,
    )
    logger.info(
        "%d of %d tools enabled (read-only: %s, max blocks per call: %s)",
        len(enabled),
        len(registry.specs),
        settings.read_only,
        f"{settings.max_blocks:,}",
    )
    return server
