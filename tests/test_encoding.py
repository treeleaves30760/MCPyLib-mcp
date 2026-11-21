import pytest

from mcpylib_mcp.encoding import (
    AIR,
    PALETTE_CHARS,
    check_xyz_blocks,
    decode_layers,
    encode_layers,
    encode_xyz,
    height_map,
    normalize_block_id,
)
from mcpylib_mcp.errors import InvalidInputError, MinecraftError


def make_grid(sx, sy, sz, fill=AIR):
    return [[[fill for _ in range(sz)] for _ in range(sy)] for _ in range(sx)]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Stone", "minecraft:stone"),
        ("minecraft:oak_log", "minecraft:oak_log"),
        ("  GRASS_BLOCK ", "minecraft:grass_block"),
        ("mymod:thing", "mymod:thing"),
    ],
)
def test_normalize_block_id(raw, expected):
    assert normalize_block_id(raw) == expected


def test_encode_layers_uses_y_layers_z_rows_x_columns():
    # 3 wide (x), 2 tall (y), 2 deep (z); every cell distinguishable by position.
    grid = make_grid(3, 2, 2)
    grid[0][0][0] = "minecraft:stone"  # west, bottom, north
    grid[2][0][0] = "minecraft:stone"  # east, bottom, north
    grid[1][0][1] = "minecraft:dirt"  # middle, bottom, south
    grid[2][1][1] = "minecraft:gold_block"  # east, top, south

    encoded = encode_layers(grid)

    palette = encoded["palette"]
    assert palette["."] == AIR
    assert palette["A"] == "minecraft:stone"  # most frequent non-air block gets "A"
    char = {block: c for c, block in palette.items()}
    stone, dirt, gold = char["minecraft:stone"], char["minecraft:dirt"], char["minecraft:gold_block"]
    assert encoded["layers"] == [
        [f"{stone}.{stone}", f".{dirt}."],  # y=0: row z=0 then row z=1
        ["...", f"..{gold}"],  # y=1
    ]
    assert encoded["counts"] == {AIR: 8, "minecraft:stone": 2, "minecraft:dirt": 1, "minecraft:gold_block": 1}


def test_encode_layers_refuses_more_block_types_than_palette_characters():
    grid = make_grid(len(PALETTE_CHARS) + 1, 1, 1)
    for x in range(len(PALETTE_CHARS) + 1):
        grid[x][0][0] = f"minecraft:block_{x}"

    with pytest.raises(InvalidInputError, match="layout='xyz'"):
        encode_layers(grid)


def test_encode_xyz_returns_palette_indices_in_edit_order():
    grid = make_grid(2, 1, 2)
    grid[1][0][0] = "minecraft:stone"

    encoded = encode_xyz(grid)

    assert encoded["palette"] == [AIR, "minecraft:stone"]
    assert encoded["blocks"] == [[[0, 0]], [[1, 0]]]
    assert encoded["counts"] == {AIR: 3, "minecraft:stone": 1}


def test_encoders_reject_malformed_server_data():
    with pytest.raises(MinecraftError, match="malformed"):
        encode_layers([[["minecraft:stone"]], [["minecraft:stone"], ["minecraft:stone"]]])


def test_decode_layers_maps_characters_to_xyz_blocks():
    chest = {"block": "minecraft:chest", "block_state": {"facing": "south"}}
    blocks, count = decode_layers(
        {"#": "stone", "C": chest, "~": None},
        [
            ["##", "~C"],  # y=0: z=0 row, z=1 row
            ["# ", "  "],  # y=1: space means "leave unchanged"
        ],
    )

    # blocks[x][y][z]
    assert blocks[0][0][0] == "stone"
    assert blocks[1][0][0] == "stone"
    assert blocks[0][0][1] is None  # explicit None in palette also skips
    assert blocks[1][0][1] == chest
    assert blocks[0][1][0] == "stone"
    assert blocks[1][1][0] is None
    assert count == 4


def test_decode_layers_round_trips_encode_layers():
    grid = make_grid(3, 2, 4)
    grid[0][0][3] = "minecraft:stone"
    grid[2][1][0] = "minecraft:glass"
    encoded = encode_layers(grid)

    blocks, count = decode_layers(encoded["palette"], encoded["layers"])

    assert blocks == grid
    assert count == 3 * 2 * 4


@pytest.mark.parametrize(
    ("palette", "layers", "message"),
    [
        ({"#": "stone"}, [], "at least one layer"),
        ({"#": "stone"}, [[]], "layers\\[0\\] has no rows"),
        ({"#": "stone"}, [["##", "#"]], "layers\\[0\\]\\[1\\] has length 1"),
        ({"#": "stone"}, [["##"], ["##", "##"]], "layers\\[1\\] has 2 rows"),
        ({"#": "stone"}, [["#X"]], "'X' at layers\\[0\\]\\[0\\]\\[1\\] is not in the palette"),
        ({"##": "stone"}, [["#"]], "single character"),
        ({" ": "stone"}, [[" "]], "reserved"),
        ({"#": "stone"}, [[""]], "empty"),
    ],
)
def test_decode_layers_reports_precise_errors(palette, layers, message):
    with pytest.raises(InvalidInputError, match=message):
        decode_layers(palette, layers)


def test_check_xyz_blocks_counts_non_null_cells():
    blocks = [[["stone", None]], [[None, {"block": "chest"}]]]

    assert check_xyz_blocks(blocks) == ((2, 1, 2), 2)


@pytest.mark.parametrize(
    ("blocks", "message"),
    [
        ([], "must not be empty"),
        ([[]], "blocks\\[0\\] must not be empty"),
        ([[["stone"]], [["stone"], ["stone"]]], "blocks\\[1\\] has 2 entries"),
        ([[["stone", "dirt"]], [["stone"]]], "blocks\\[1\\]\\[0\\] has 1 entries"),
    ],
)
def test_check_xyz_blocks_rejects_ragged_arrays(blocks, message):
    with pytest.raises(InvalidInputError, match=message):
        check_xyz_blocks(blocks)


def test_height_map_finds_highest_non_air_block_per_column():
    # x: 2 columns, y: 60..65 (6 levels), z: 2 rows
    grid = make_grid(2, 6, 2)
    for y in range(0, 4):  # y = 60..63 stone everywhere except column (1, 1)
        for x, z in [(0, 0), (1, 0), (0, 1)]:
            grid[x][y][z] = "minecraft:stone"
    grid[0][4][0] = "minecraft:grass_block"  # (x=0, z=0) top at y=64
    grid[1][5][0] = "minecraft:oak_leaves"  # (x=1, z=0) leaves floating at y=65

    result = height_map(grid, y_origin=60, ignore=set())

    assert result["heights"] == [[64, 65], [63, None]]  # rows are z, columns are x
    palette = result["surface_palette"]
    char = {block: c for c, block in palette.items()}
    assert result["surface"] == [
        char["minecraft:grass_block"] + char["minecraft:oak_leaves"],
        char["minecraft:stone"] + " ",
    ]


def test_height_map_can_ignore_foliage():
    grid = make_grid(1, 4, 1)
    grid[0][0][0] = "minecraft:dirt"
    grid[0][3][0] = "minecraft:oak_leaves"

    result = height_map(grid, y_origin=10, ignore={"minecraft:oak_leaves"})

    assert result["heights"] == [[10]]
