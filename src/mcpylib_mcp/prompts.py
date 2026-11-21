"""MCP prompts: reusable task templates that walk the model through common jobs."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .config import Settings

BUILD_REQUIRES = {"build_from_layers", "fill_region", "get_height_map"}
SURVEY_REQUIRES = {"get_height_map", "get_blocks"}


def register_prompts(server: MCPServer, settings: Settings, enabled_tools: list[str]) -> None:
    """Register the prompts whose tools are all enabled (e.g. no building prompt in read-only mode)."""
    enabled = set(enabled_tools)
    limit = f"{settings.max_blocks:,}"

    if BUILD_REQUIRES <= enabled:

        @server.prompt(
            name="build_structure",
            title="Build a structure",
            description="Plan and build a structure in the world: survey the site, prepare it, build, and verify.",
        )
        def build_structure(
            description: Annotated[str, Field(description="What to build, e.g. 'a small oak cabin with a porch'.")],
            location: Annotated[
                str, Field(description="Where: coordinates such as '120 64 -40', or 'next to Steve'.")
            ] = "",
        ) -> str:
            where = location or (
                "not given: ask the user, or build next to the first online player (get_players, get_player_position)"
            )
            return f"""Build this in Minecraft: {description}
Location: {where}.

Work in this order:
1. Turn the location into coordinates. If it names a player, use get_player_position.
2. Survey the footprint with get_height_map (keep y_min/y_max within about 20 blocks of the ground) and, if
   needed, get_blocks with layout='summary' to spot water or existing builds. Never overwrite player builds.
3. Plan the size, a palette of materials and the orientation (entrances facing open ground). Tell the user
   the plan and the corner coordinates in one or two sentences.
4. Prepare the site: fill_region with air to clear the space above the ground, and solid blocks to level it.
5. Build: fill_region for solid boxes (walls, floors, foundations), build_from_layers for detailed parts
   (windows, doors with block_state, roofs, decoration). Doors need a bottom and a top half.
6. Verify: read the key layers back with get_blocks and fix anything that is off.
7. Report what you built and where (corner coordinates).

Conventions: +X is east, +Z is south, +Y is up. In build_from_layers the layers go bottom to top, the rows
north to south and the characters west to east; '.' is air and ' ' leaves a block unchanged. Each call may
touch at most {limit} blocks, so split large builds into sections. The resource minecraft://guide/building
has more detail."""

    if SURVEY_REQUIRES <= enabled:

        @server.prompt(
            name="survey_area",
            title="Survey an area",
            description="Inspect an area without changing it: terrain, materials, water, builds and good sites.",
        )
        def survey_area(
            location: Annotated[
                str, Field(description="Centre: coordinates such as '120 64 -40', or a player name.")
            ] = "",
            radius: Annotated[
                int, Field(ge=1, le=256, description="Half-width of the square to survey, in blocks.")
            ] = 16,
        ) -> str:
            centre = location or "the first online player's position (get_players, then get_player_position)"
            return f"""Survey this Minecraft area and report on it without changing anything.
Centre: {centre}. Radius: {radius} blocks (a square of side {2 * radius + 1}).

1. Turn the centre into coordinates (get_player_position if it names a player).
2. Call get_height_map over the square, with y_min about 30 blocks below and y_max about 40 above the centre Y.
   Each call may scan at most {limit} blocks, so split the square into tiles if needed. If trees hide the
   ground, repeat with ignore_blocks such as ["oak_leaves", "birch_leaves", "spruce_leaves", "short_grass"].
3. Use get_blocks with layout='summary' on a few slices to learn what the area is made of: water, sand, stone,
   ores near the surface, or player-made blocks such as planks, glass or bricks.
4. Optionally use locate_structure to look for villages or other structures nearby.

Report concisely: the height range and flat areas (with coordinates), water and notable blocks, signs of
player builds, and the best spots to build."""
