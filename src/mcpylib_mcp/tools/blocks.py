"""Block tools: read, write, fill, clone and bulk-build regions."""

from typing import Annotated, Any, Literal

from pydantic import Field

from ..encoding import (
    check_xyz_blocks,
    decode_layers,
    encode_layers,
    encode_xyz,
    height_map,
    normalize_block_id,
    summarize,
)
from ..errors import InvalidInputError, MinecraftError
from ..params import (
    X1,
    X2,
    XZ_LIMIT,
    Y1,
    Y2,
    Y_MAX,
    Y_MIN,
    Z1,
    Z2,
    BlockId,
    BlockSpec,
    BlockState,
    Nbt,
    X,
    Y,
    Z,
    block_value,
    box,
    state_strings,
)
from ..registry import ToolRegistry, ToolResult, ok
from ..safety import enforce_block_limit, region_volume

GROUP = "blocks"
CLONE_PLUGIN_LIMIT = 32_768  # hard limit inside the MCPyLib plugin

BlockEntry = BlockId | BlockSpec | None
Layout = Annotated[
    Literal["layers", "xyz", "summary"],
    Field(
        description=(
            "'layers' (default): character palette + layers[y][z] strings, the format build_from_layers "
            "accepts. 'xyz': palette indices as blocks[x][y][z], the edit_blocks format. 'summary': block counts only."
        )
    ),
]
DestX = Annotated[int, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="X where the box's lowest-X edge lands.")]
DestY = Annotated[int, Field(ge=Y_MIN, le=Y_MAX, description="Y where the box's bottom lands.")]
DestZ = Annotated[int, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Z where the box's lowest-Z edge lands.")]


def _fetch_grid(bridge: Any, low: dict[str, int], high: dict[str, int]) -> Any:
    grid = bridge.call("getblocks", low["x"], low["y"], low["z"], high["x"], high["y"], high["z"])
    expected = (high["x"] - low["x"] + 1, high["y"] - low["y"] + 1, high["z"] - low["z"] + 1)
    try:
        actual = (len(grid), len(grid[0]), len(grid[0][0]))
    except (TypeError, IndexError):
        actual = None
    if actual != expected:
        raise MinecraftError(f"The Minecraft server returned a block grid of size {actual}, expected {expected}.")
    return grid


def register(reg: ToolRegistry) -> None:
    bridge, limit = reg.bridge, reg.settings.max_blocks

    @reg.tool(GROUP, "Get block", read_only=True)
    def get_block(x: X, y: Y, z: Z) -> ToolResult:
        """Return the block id at one position, e.g. 'minecraft:stone' (block states are not included)."""
        return ok({"x": x, "y": y, "z": z, "block": bridge.call("getblock", x, y, z)})

    @reg.tool(GROUP, "Read blocks in a box", read_only=True)
    def get_blocks(x1: X1, y1: Y1, z1: Z1, x2: X2, y2: Y2, z2: Z2, layout: Layout = "layers") -> ToolResult:
        """Read every block in a box (corners inclusive, any order; at most {max_blocks} blocks).

        The default 'layers' layout returns `palette` (character -> block id) and `layers`: one entry per Y
        from the bottom up, each a list of row strings from north to south (+Z), each row read west to east
        (+X). '.' is air. It is the exact input format of build_from_layers, so you can edit the strings and
        write them back. `counts` gives the number of each block. Keep raw reads small (16x16x16 is plenty);
        use layout='summary' or get_height_map for big areas.
        """
        volume = region_volume(x1, y1, z1, x2, y2, z2)
        enforce_block_limit(volume, limit, "This read")
        low, high = box(x1, y1, z1, x2, y2, z2)
        grid = _fetch_grid(bridge, low, high)
        size = {axis: high[axis] - low[axis] + 1 for axis in "xyz"}
        result: dict[str, Any] = {"origin": low, "size": size, "volume": volume}
        if layout == "layers":
            result |= encode_layers(grid)
        elif layout == "xyz":
            result |= encode_xyz(grid)
        else:
            result |= summarize(grid)
        return ok(result)

    @reg.tool(GROUP, "Map surface heights", read_only=True)
    def get_height_map(
        x1: X1,
        z1: Z1,
        x2: X2,
        z2: Z2,
        y_min: Annotated[
            int,
            Field(
                ge=Y_MIN,
                le=Y_MAX,
                description="Lowest Y to scan; narrow the range around the expected ground.",
            ),
        ] = -64,
        y_max: Annotated[int, Field(ge=Y_MIN, le=Y_MAX, description="Highest Y to scan.")] = 319,
        ignore_blocks: Annotated[
            list[BlockId] | None,
            Field(
                max_length=64,
                description=(
                    "Block ids to treat as empty, e.g. ['water', 'oak_leaves', 'short_grass'] to find solid "
                    "ground under water or trees. Air is always empty."
                ),
            ),
        ] = None,
    ) -> ToolResult:
        """Find the ground: for each column of an X/Z area, the Y of the highest block that is not air.

        `heights[z][x]` is an absolute Y (null for an empty column): rows go north to south (+Z), entries west
        to east (+X). `surface` uses the same layout with characters from `surface_palette`. Build on a column
        at heights + 1. Scans (area x height) blocks, at most {max_blocks}; narrow y_min/y_max for big areas.
        """
        if y_min > y_max:
            raise InvalidInputError("y_min must not be greater than y_max.")
        volume = region_volume(x1, y_min, z1, x2, y_max, z2)
        enforce_block_limit(volume, limit, "This scan")
        low, high = box(x1, y_min, z1, x2, y_max, z2)
        grid = _fetch_grid(bridge, low, high)
        result = height_map(grid, y_min, {normalize_block_id(block) for block in ignore_blocks or ()})
        found = [y for row in result["heights"] for y in row if y is not None]
        return ok(
            {
                "origin": {"x": low["x"], "z": low["z"]},
                "size": {"x": high["x"] - low["x"] + 1, "z": high["z"] - low["z"] + 1},
                "y_range": [y_min, y_max],
                **result,
                "lowest": min(found) if found else None,
                "highest": max(found) if found else None,
            }
        )

    @reg.tool(GROUP, "Set block", destructive=True, idempotent=True)
    def set_block(x: X, y: Y, z: Z, block: BlockId, block_state: BlockState = None, nbt: Nbt = None) -> ToolResult:
        """Place one block, replacing what is there. For more than a handful of blocks use fill_region or
        build_from_layers. Doors and beds need both halves placed explicitly."""
        placed = bridge.call("setblock", x, y, z, block, block_state=state_strings(block_state), nbt=nbt)
        return ok({"x": x, "y": y, "z": z, "block": block, "placed": placed == 1})

    @reg.tool(GROUP, "Fill a box", destructive=True, idempotent=True)
    def fill_region(x1: X1, y1: Y1, z1: Z1, x2: X2, y2: Y2, z2: Z2, block: BlockId) -> ToolResult:
        """Fill a box (corners inclusive, any order) with one block, replacing everything inside; use 'air'
        to clear an area. Refuses boxes larger than {max_blocks} blocks. Blocks are placed without physics,
        so sand does not fall and water does not flow until neighbours update."""
        enforce_block_limit(region_volume(x1, y1, z1, x2, y2, z2), limit, "This fill")
        low, high = box(x1, y1, z1, x2, y2, z2)
        changed = bridge.call("fill", x1, y1, z1, x2, y2, z2, block)
        return ok({"from": low, "to": high, "block": block, "blocks_changed": changed})

    @reg.tool(GROUP, "Clone a box", destructive=True, idempotent=True)
    def clone_region(
        x1: X1, y1: Y1, z1: Z1, x2: X2, y2: Y2, z2: Z2, dest_x: DestX, dest_y: DestY, dest_z: DestZ
    ) -> ToolResult:
        """Copy a box of blocks (types and states) so that its lowest corner lands at (dest_x, dest_y,
        dest_z), overwriting the destination. Container contents and sign text are not copied. Source and
        destination must not overlap. At most 32,768 blocks (plugin limit) and at most {max_blocks}."""
        volume = region_volume(x1, y1, z1, x2, y2, z2)
        enforce_block_limit(volume, min(limit, CLONE_PLUGIN_LIMIT), "This clone")
        low, high = box(x1, y1, z1, x2, y2, z2)
        dest_low = {"x": dest_x, "y": dest_y, "z": dest_z}
        dest_high = {axis: dest_low[axis] + high[axis] - low[axis] for axis in "xyz"}
        overlaps = all(dest_low[a] <= high[a] and low[a] <= dest_high[a] for a in "xyz")
        if overlaps and dest_low != low:
            raise InvalidInputError(
                "The source and destination boxes overlap, which the plugin would copy incorrectly. Clone to a "
                "free area first, or read the source with get_blocks and rebuild it with build_from_layers."
            )
        cloned = bridge.call("clone", x1, y1, z1, x2, y2, z2, dest_x, dest_y, dest_z)
        return ok(
            {
                "source": {"from": low, "to": high},
                "destination": {"from": dest_low, "to": dest_high},
                "blocks_cloned": cloned,
            }
        )

    @reg.tool(GROUP, "Edit blocks from a 3D array", destructive=True, idempotent=True)
    def edit_blocks(
        x: Annotated[int, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="X of the array's lowest corner.")],
        y: Annotated[int, Field(ge=Y_MIN, le=Y_MAX, description="Y of the array's lowest corner.")],
        z: Annotated[int, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Z of the array's lowest corner.")],
        blocks: Annotated[
            list[list[list[BlockEntry]]],
            Field(
                description=(
                    "Rectangular array indexed blocks[x][y][z] relative to the corner. Each entry is a block id, "
                    "an object {block, block_state?, nbt?}, or null to leave that position unchanged."
                )
            ),
        ],
    ) -> ToolResult:
        """Place many different blocks in one call from a 3D array (MCPyLib's bulk edit). build_from_layers
        is usually easier to write. Refuses arrays whose bounding box exceeds {max_blocks} blocks."""
        (sx, sy, sz), _ = check_xyz_blocks(blocks)
        enforce_block_limit(sx * sy * sz, limit, "This edit")
        payload = [[[block_value(entry) for entry in column] for column in plane] for plane in blocks]
        placed = bridge.call("edit", x, y, z, payload)
        return ok({"origin": {"x": x, "y": y, "z": z}, "size": {"x": sx, "y": sy, "z": sz}, "blocks_placed": placed})

    @reg.tool(GROUP, "Build from text layers", destructive=True, idempotent=True)
    def build_from_layers(
        x: Annotated[int, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="X of the west (lowest X) edge.")],
        y: Annotated[int, Field(ge=Y_MIN, le=Y_MAX, description="Y of the bottom layer.")],
        z: Annotated[int, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Z of the north (lowest Z) edge.")],
        palette: Annotated[
            dict[str, BlockEntry],
            Field(
                description=(
                    "Maps single characters to a block id, an object {block, block_state?, nbt?}, or null (leave "
                    "unchanged). A space always means 'leave unchanged' and cannot be redefined."
                )
            ),
        ],
        layers: Annotated[
            list[list[str]],
            Field(
                min_length=1,
                description=(
                    "Horizontal slices from bottom to top. Each slice is a list of rows from north to south (+Z); "
                    "each row is a string read west to east (+X), one character per block. Every slice needs the "
                    "same number of rows and every row the same length."
                ),
            ),
        ],
    ) -> ToolResult:
        """Build a structure from text layers, like floor plans stacked bottom to top: character k of row j
        of layer i becomes block (x + k, y + i, z + j). Ideal for houses, statues and pixel art; use
        fill_region for big solid volumes. get_blocks returns this same format, so a region can be read,
        edited and written back. Refuses structures whose bounding box exceeds {max_blocks} blocks.

        Example: palette {"#": "stone_bricks", "G": "glass", ".": "air"} with
        layers [["###", "#.#", "###"], ["#G#", "G.G", "#G#"]] builds a 3x3 stone ring with a glass ring on top.
        """
        # Check the bounding box before decoding so oversized input is never expanded in memory.
        sy = len(layers)
        sz = len(layers[0])
        sx = len(layers[0][0]) if sz else 0
        enforce_block_limit(sx * sy * sz, limit, "This build")
        blocks, _ = decode_layers({char: block_value(entry) for char, entry in palette.items()}, layers)
        placed = bridge.call("edit", x, y, z, blocks)
        return ok(
            {
                "origin": {"x": x, "y": y, "z": z},
                "size": {"x": sx, "y": sy, "z": sz},
                "far_corner": {"x": x + sx - 1, "y": y + sy - 1, "z": z + sz - 1},
                "blocks_placed": placed,
            }
        )
