"""MCP resources: read-only context that a client can attach to a conversation."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError

from .bridge import MinecraftBridge
from .config import Settings
from .errors import MinecraftError
from .tools.world import describe_time

STATUS_URI = "minecraft://server/status"
PLAYER_URI = "minecraft://players/{username}"
GUIDE_URI = "minecraft://guide/building"

BUILDING_GUIDE = """\
# Building with mcpylib-mcp

## Coordinates
- +X is east, -X west; +Z is south, -Z north; +Y is up.
- Overworld blocks exist from Y -64 to Y 319. A player's position is their feet: the block they stand on is
  at y - 1.
- Block, world and particle tools act on the server's main world (the overworld), even if a player is
  elsewhere. Player and entity tools act wherever that player or entity is.

## Block ids and states
- Use Minecraft ids such as `minecraft:stone` or `oak_planks` (the namespace is optional).
- `block_state` takes any vanilla property of the block: `facing`, `axis`, `half` (stairs: top/bottom),
  `shape`, `type` (slabs), `hinge`, `lit`, `rotation` (0-15, or a compass name such as north_north_east),
  ... A property the block doesn't have is an error.
- Doors, beds and tall flowers are two blocks. In `edit_blocks` and `build_from_layers` give the lower half
  (door `half: lower`) or the bed foot and the plugin adds the other half (plugin 1.2.1+). `set_block` places
  only the block you name, so set both halves there.
- Only `CustomName` (containers) and `Text1`-`Text4` (sign lines) NBT data is applied.

## Choosing a tool
| Job | Tool |
| --- | --- |
| One block | `set_block` |
| Solid boxes, floors, walls, clearing an area with air | `fill_region` |
| Detailed structures with mixed materials | `build_from_layers` |
| Copying something that already exists | `clone_region` (at most 32,768 blocks, no overlap) |
| Looking around | `get_block`, `get_blocks`, `get_height_map` |

## The layers format (`get_blocks` output and `build_from_layers` input)
```json
{
  "palette": {"#": "stone_bricks", "G": "glass", ".": "air"},
  "layers": [
    ["###", "#.#", "###"],
    ["#G#", "G.G", "#G#"]
  ]
}
```
- `layers[i]` is the slice at y + i (bottom first), `layers[i][j]` the row at z + j (north first), and
  character k of that row is the block at x + k (west first).
- `.` is air and clears blocks; a space leaves the existing block unchanged.
- Every slice needs the same number of rows and every row the same length.

## Workflow
1. Find the site: `get_player_position`, then `get_height_map` over the footprint (keep y_min/y_max tight).
2. Prepare it: `fill_region` with air to clear space above the ground, and solid blocks to level it.
3. Build solid parts with `fill_region`, then details with `build_from_layers`.
4. Verify with `get_blocks` and fix differences.

## Limits
- Each call may read or change at most {max_blocks} blocks (MCPYLIB_MAX_BLOCKS); split bigger builds into
  sections.
- Changes are immediate and cannot be undone. Check what is there before replacing it.
"""


def building_guide(settings: Settings) -> str:
    return BUILDING_GUIDE.replace("{max_blocks}", f"{settings.max_blocks:,}")


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_resources(
    server: MCPServer, bridge: MinecraftBridge, settings: Settings, enabled_tools: list[str]
) -> None:
    @server.resource(
        STATUS_URI,
        name="server_status",
        title="Minecraft server status",
        description="Online players, time of day, world border, and this MCP server's limits. Never fails: "
        "if the plugin is unreachable it reports connected=false with the reason.",
        mime_type="application/json",
    )
    def server_status() -> str:
        limits = {
            "read_only": settings.read_only,
            "max_blocks": settings.max_blocks,
            "tools_enabled": len(enabled_tools),
        }
        try:
            state: dict[str, Any] = {
                "connected": True,
                "players": bridge.call("list"),
                "time": describe_time(bridge.call("time", "query")),
                "world_border": bridge.call("worldborder", "get"),
            }
        except MinecraftError as exc:
            state = {"connected": False, "error": str(exc)}
        return _json({"target": bridge.target, **state, "mcp": limits})

    @server.resource(
        PLAYER_URI,
        name="player",
        title="Online player",
        description="An online player's UUID, game mode, block position and experience.",
        mime_type="application/json",
    )
    def player(username: str) -> str:
        try:
            x, y, z = bridge.call("getPos", username)
            online = bridge.call("list")
            experience = bridge.call("experience", username, "query", 0, "points")
        except MinecraftError as exc:
            if "not found" in str(exc).lower():
                raise ResourceNotFoundError(str(exc)) from exc
            raise ResourceError(str(exc)) from exc
        info = next((p for p in online.get("players", []) if p.get("name") == username), {})
        return _json(
            {
                "name": username,
                "uuid": info.get("uuid"),
                "gamemode": info.get("gamemode"),
                "position": {"x": x, "y": y, "z": z},
                "experience": experience,
            }
        )

    @server.resource(
        GUIDE_URI,
        name="building_guide",
        title="Building guide",
        description="Coordinates, block states, the layers format and a building workflow for these tools.",
        mime_type="text/markdown",
    )
    def guide() -> str:
        return building_guide(settings)
