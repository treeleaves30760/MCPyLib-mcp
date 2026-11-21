import pytest
from helpers import connect, error_text, ok_data

pytestmark = pytest.mark.anyio


async def test_set_block_then_get_block(fake):
    async with connect(fake) as client:
        placed = ok_data(await client.call_tool("set_block", {"x": 1, "y": 70, "z": 2, "block": "oak_planks"}))
        got = ok_data(await client.call_tool("get_block", {"x": 1, "y": 70, "z": 2}))

    assert placed["placed"] is True
    assert got == {"x": 1, "y": 70, "z": 2, "block": "minecraft:oak_planks"}
    assert fake.last("setblock") == {"x": 1, "y": 70, "z": 2, "block": "oak_planks"}


async def test_set_block_forwards_state_and_nbt_as_strings(fake):
    async with connect(fake) as client:
        ok_data(
            await client.call_tool(
                "set_block",
                {
                    "x": 0,
                    "y": 70,
                    "z": 0,
                    "block": "chest",
                    "block_state": {"facing": "north", "waterlogged": True},
                    "nbt": {"CustomName": "Loot"},
                },
            )
        )

    params = fake.last("setblock")
    assert params["block_state"] == {"facing": "north", "waterlogged": "true"}
    assert params["nbt"] == {"CustomName": "Loot"}


async def test_fill_region_changes_every_block_in_the_box(fake):
    async with connect(fake) as client:
        data = ok_data(
            await client.call_tool(
                "fill_region", {"x1": 2, "y1": 70, "z1": 2, "x2": 0, "y2": 72, "z2": 0, "block": "glass"}
            )
        )

    assert data["blocks_changed"] == 27
    assert data["from"] == {"x": 0, "y": 70, "z": 0}
    assert data["to"] == {"x": 2, "y": 72, "z": 2}
    assert fake.block_at(1, 71, 1) == "minecraft:glass"


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("fill_region", {"x1": 0, "y1": 0, "z1": 0, "x2": 9, "y2": 9, "z2": 9, "block": "stone"}),
        ("get_blocks", {"x1": 0, "y1": 0, "z1": 0, "x2": 9, "y2": 9, "z2": 9}),
        (
            "clone_region",
            {"x1": 0, "y1": 0, "z1": 0, "x2": 9, "y2": 9, "z2": 9, "dest_x": 50, "dest_y": 0, "dest_z": 0},
        ),
        ("get_height_map", {"x1": 0, "z1": 0, "x2": 9, "z2": 9, "y_min": 0, "y_max": 9}),
        ("fill_biome", {"x1": 0, "y1": 0, "z1": 0, "x2": 9, "y2": 9, "z2": 9, "biome": "minecraft:desert"}),
        ("edit_blocks", {"x": 0, "y": 0, "z": 0, "blocks": [[[None] * 10] * 10] * 10}),
        (
            "build_from_layers",
            {"x": 0, "y": 0, "z": 0, "palette": {"#": "stone"}, "layers": [["#" * 10] * 10] * 10},
        ),
    ],
)
async def test_block_limit_is_enforced_before_contacting_the_server(fake, tool, arguments):
    async with connect(fake, max_blocks=999) as client:
        text = error_text(await client.call_tool(tool, arguments))

    assert "1,000 blocks" in text
    assert "999" in text
    assert "MCPYLIB_MAX_BLOCKS" in text
    assert fake.requests == []


async def test_clone_region_respects_the_plugin_maximum(fake):
    async with connect(fake, max_blocks=1_000_000) as client:
        text = error_text(
            await client.call_tool(
                "clone_region",
                {
                    "x1": 0,
                    "y1": 0,
                    "z1": 0,
                    "x2": 39,
                    "y2": 39,
                    "z2": 39,
                    "dest_x": 100,
                    "dest_y": 0,
                    "dest_z": 0,
                },
            )
        )

    assert "32,768" in text
    assert fake.requests == []


async def test_clone_region_refuses_overlapping_boxes(fake):
    async with connect(fake) as client:
        text = error_text(
            await client.call_tool(
                "clone_region",
                {
                    "x1": 0,
                    "y1": 64,
                    "z1": 0,
                    "x2": 4,
                    "y2": 64,
                    "z2": 4,
                    "dest_x": 2,
                    "dest_y": 64,
                    "dest_z": 2,
                },
            )
        )

    assert "overlap" in text
    assert fake.requests == []


async def test_clone_region_copies_blocks(fake):
    fake.blocks[(0, 70, 0)] = "minecraft:gold_block"
    async with connect(fake) as client:
        data = ok_data(
            await client.call_tool(
                "clone_region",
                {
                    "x1": 1,
                    "y1": 71,
                    "z1": 1,
                    "x2": 0,
                    "y2": 70,
                    "z2": 0,
                    "dest_x": 10,
                    "dest_y": 80,
                    "dest_z": 10,
                },
            )
        )

    assert data["blocks_cloned"] == 8
    assert data["destination"] == {"from": {"x": 10, "y": 80, "z": 10}, "to": {"x": 11, "y": 81, "z": 11}}
    assert fake.block_at(10, 80, 10) == "minecraft:gold_block"


async def test_get_blocks_layers_layout(fake):
    fake.blocks[(1, 64, 0)] = "minecraft:stone"
    async with connect(fake) as client:
        data = ok_data(await client.call_tool("get_blocks", {"x1": 0, "y1": 63, "z1": 0, "x2": 2, "y2": 64, "z2": 1}))

    assert data["origin"] == {"x": 0, "y": 63, "z": 0}
    assert data["size"] == {"x": 3, "y": 2, "z": 2}
    assert data["volume"] == 12
    char = {block: c for c, block in data["palette"].items()}
    grass, stone = char["minecraft:grass_block"], char["minecraft:stone"]
    assert data["layers"] == [[grass * 3, grass * 3], [f".{stone}.", "..."]]
    assert data["counts"] == {"minecraft:grass_block": 6, "minecraft:air": 5, "minecraft:stone": 1}


async def test_get_blocks_xyz_and_summary_layouts(fake):
    async with connect(fake) as client:
        xyz = ok_data(
            await client.call_tool(
                "get_blocks", {"x1": 0, "y1": 63, "z1": 0, "x2": 1, "y2": 64, "z2": 0, "layout": "xyz"}
            )
        )
        summary = ok_data(
            await client.call_tool(
                "get_blocks", {"x1": 0, "y1": 63, "z1": 0, "x2": 1, "y2": 64, "z2": 0, "layout": "summary"}
            )
        )

    assert xyz["palette"] == ["minecraft:air", "minecraft:grass_block"]
    assert xyz["blocks"] == [[[1], [0]], [[1], [0]]]
    assert "blocks" not in summary and "layers" not in summary
    assert summary["counts"] == {"minecraft:air": 2, "minecraft:grass_block": 2}


async def test_edit_blocks_places_an_xyz_array(fake):
    chest = {"block": "chest", "block_state": {"facing": "east"}}
    async with connect(fake) as client:
        data = ok_data(
            await client.call_tool(
                "edit_blocks", {"x": 10, "y": 80, "z": 10, "blocks": [[["stone", None]], [[chest, "glass"]]]}
            )
        )

    assert data["blocks_placed"] == 3
    assert data["size"] == {"x": 2, "y": 1, "z": 2}
    assert fake.block_at(10, 80, 10) == "minecraft:stone"
    assert (10, 80, 11) not in fake.blocks
    assert fake.block_at(11, 80, 10) == "minecraft:chest"
    assert fake.block_specs[(11, 80, 10)]["block_state"] == {"facing": "east"}
    assert fake.block_at(11, 80, 11) == "minecraft:glass"


async def test_edit_blocks_rejects_ragged_arrays(fake):
    async with connect(fake) as client:
        text = error_text(
            await client.call_tool(
                "edit_blocks", {"x": 0, "y": 80, "z": 0, "blocks": [[["stone", "dirt"]], [["stone"]]]}
            )
        )

    assert "blocks[1][0]" in text
    assert fake.requests == []


async def test_build_from_layers_maps_rows_to_z_and_characters_to_x(fake):
    async with connect(fake) as client:
        data = ok_data(
            await client.call_tool(
                "build_from_layers",
                {
                    "x": 100,
                    "y": 70,
                    "z": 200,
                    "palette": {"A": "stone", "B": "glass", "C": "gold_block", "D": "diamond_block"},
                    "layers": [["AB", "C "], ["D ", "  "]],
                },
            )
        )

    assert data["blocks_placed"] == 4
    assert data["size"] == {"x": 2, "y": 2, "z": 2}
    assert fake.block_at(100, 70, 200) == "minecraft:stone"  # layer 0, row 0, column 0
    assert fake.block_at(101, 70, 200) == "minecraft:glass"  # column 1 -> +X
    assert fake.block_at(100, 70, 201) == "minecraft:gold_block"  # row 1 -> +Z
    assert fake.block_at(100, 71, 200) == "minecraft:diamond_block"  # layer 1 -> +Y
    assert (101, 70, 201) not in fake.blocks  # space leaves the block unchanged


async def test_get_blocks_output_can_be_written_back_with_build_from_layers(fake):
    fake.blocks.update({(0, 70, 0): "minecraft:stone", (1, 71, 1): "minecraft:glass", (2, 70, 1): "minecraft:dirt"})
    async with connect(fake) as client:
        region = ok_data(await client.call_tool("get_blocks", {"x1": 0, "y1": 70, "z1": 0, "x2": 2, "y2": 71, "z2": 1}))
        ok_data(
            await client.call_tool(
                "build_from_layers",
                {"x": 50, "y": 90, "z": 50, "palette": region["palette"], "layers": region["layers"]},
            )
        )

    for dx in range(3):
        for dy in range(2):
            for dz in range(2):
                assert fake.block_at(50 + dx, 90 + dy, 50 + dz) == fake.block_at(dx, 70 + dy, dz)


async def test_build_from_layers_reports_unknown_characters(fake):
    async with connect(fake) as client:
        text = error_text(
            await client.call_tool(
                "build_from_layers", {"x": 0, "y": 70, "z": 0, "palette": {"#": "stone"}, "layers": [["#?"]]}
            )
        )

    assert "'?' at layers[0][0][1]" in text
    assert fake.requests == []


async def test_get_height_map_finds_the_ground(fake):
    fake.blocks[(2, 70, 1)] = "minecraft:oak_leaves"
    async with connect(fake) as client:
        data = ok_data(
            await client.call_tool("get_height_map", {"x1": 0, "z1": 0, "x2": 2, "z2": 1, "y_min": 60, "y_max": 80})
        )
        ignoring = ok_data(
            await client.call_tool(
                "get_height_map",
                {
                    "x1": 0,
                    "z1": 0,
                    "x2": 2,
                    "z2": 1,
                    "y_min": 60,
                    "y_max": 80,
                    "ignore_blocks": ["oak_leaves"],
                },
            )
        )

    assert data["origin"] == {"x": 0, "z": 0}
    assert data["size"] == {"x": 3, "z": 2}
    assert data["heights"] == [[63, 63, 63], [63, 63, 70]]
    assert data["lowest"] == 63 and data["highest"] == 70
    assert ignoring["heights"] == [[63, 63, 63], [63, 63, 63]]


async def test_get_height_map_rejects_inverted_y_range(fake):
    async with connect(fake) as client:
        text = error_text(
            await client.call_tool("get_height_map", {"x1": 0, "z1": 0, "x2": 1, "z2": 1, "y_min": 80, "y_max": 60})
        )

    assert "y_min" in text
    assert fake.requests == []
