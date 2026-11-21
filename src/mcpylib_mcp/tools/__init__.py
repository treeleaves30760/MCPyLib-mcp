"""MCP tools, grouped by what they act on."""

from ..registry import ToolRegistry
from . import admin, blocks, chat, entities, players, scoreboard, world

GROUPS = ("server", "blocks", "players", "world", "entities", "chat", "scoreboard")


def register_all(registry: ToolRegistry) -> None:
    """Add every tool to ``registry`` (filtering happens later, at install time)."""
    for module in (admin, blocks, players, world, entities, chat, scoreboard):
        module.register(registry)
