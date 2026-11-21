import re

import pytest
from helpers import connect

pytestmark = pytest.mark.anyio

# The public tool surface: group -> {tool name: is read-only}.
CATALOG: dict[str, dict[str, bool]] = {
    "server": {"get_players": True, "run_command": False},
    "blocks": {
        "get_block": True,
        "get_blocks": True,
        "get_height_map": True,
        "set_block": False,
        "fill_region": False,
        "clone_region": False,
        "edit_blocks": False,
        "build_from_layers": False,
    },
    "players": {
        "get_player_position": True,
        "teleport_player": False,
        "set_gamemode": False,
        "give_item": False,
        "get_inventory": True,
        "set_inventory_slot": False,
        "clear_inventory": False,
        "enchant_held_item": False,
        "apply_effect": False,
        "clear_effects": False,
        "get_experience": True,
        "update_experience": False,
        "set_spawnpoint": False,
        "get_advancement": True,
        "set_advancement": False,
        "spread_players": False,
    },
    "world": {
        "get_time": True,
        "set_time": False,
        "set_weather": False,
        "set_difficulty": False,
        "get_gamerule": True,
        "set_gamerule": False,
        "set_world_spawn": False,
        "set_default_gamemode": False,
        "get_world_border": True,
        "set_world_border": False,
        "get_chunk_force_loaded": True,
        "set_chunk_force_loaded": False,
        "fill_biome": False,
        "locate_structure": True,
        "place_feature": False,
        "place_structure": False,
        "place_jigsaw": False,
        "place_template": False,
        "spawn_loot": False,
    },
    "entities": {
        "summon_entity": False,
        "kill_entities": False,
        "remove_entity": False,
        "get_entity": True,
        "teleport_entity": False,
        "set_entity_velocity": False,
        "set_entity_rotation": False,
        "set_entity_ai": False,
        "set_entity_target": False,
        "get_entity_equipment": True,
        "set_entity_equipment": False,
        "damage_entity": False,
        "ride_entity": False,
        "get_entity_attribute": True,
        "set_entity_attribute": False,
        "get_entity_tags": True,
        "update_entity_tags": False,
        "get_villager": True,
        "set_villager_profession": False,
        "set_villager_trades": False,
    },
    "chat": {
        "broadcast_message": False,
        "send_message": False,
        "send_rich_message": False,
        "show_title": False,
        "play_sound": False,
        "stop_sound": False,
        "spawn_particles": False,
    },
    "scoreboard": {
        "create_objective": False,
        "remove_objective": False,
        "set_objective_display": False,
        "set_score": False,
        "get_score": True,
        "list_teams": True,
        "create_team": False,
        "remove_team": False,
        "update_team_members": False,
        "set_team_option": False,
        "list_bossbars": True,
        "create_bossbar": False,
        "update_bossbar": False,
        "remove_bossbar": False,
    },
}
ALL_TOOLS = {name: ro for group in CATALOG.values() for name, ro in group.items()}
READ_ONLY_TOOLS = {name for name, ro in ALL_TOOLS.items() if ro}

# Tools that can irreversibly delete or overwrite world/player state.
DESTRUCTIVE = {
    "run_command",
    "set_block",
    "fill_region",
    "clone_region",
    "edit_blocks",
    "build_from_layers",
    "set_inventory_slot",
    "clear_inventory",
    "set_advancement",
    "fill_biome",
    "place_feature",
    "place_structure",
    "place_jigsaw",
    "place_template",
    "kill_entities",
    "remove_entity",
    "set_entity_equipment",  # the replaced items are lost
    "damage_entity",
    "set_villager_profession",  # vanilla resets a villager's trades when its profession changes
    "set_villager_trades",
    "remove_objective",
    "set_score",
    "remove_team",
    "remove_bossbar",
}


async def list_tools(fake, **overrides):
    async with connect(fake, **overrides) as client:
        return {tool.name: tool for tool in (await client.list_tools()).tools}


async def test_every_tool_is_registered_by_default(fake):
    tools = await list_tools(fake)

    assert set(tools) == set(ALL_TOOLS)
    assert len(tools) == 86


async def test_names_titles_and_descriptions(fake):
    for name, tool in (await list_tools(fake)).items():
        assert re.fullmatch(r"[a-z][a-z0-9_]{2,63}", name)
        assert tool.title, name
        assert tool.description and len(tool.description) >= 40, name


async def test_annotations_describe_side_effects(fake):
    for name, tool in (await list_tools(fake)).items():
        hints = tool.annotations
        assert hints is not None, name
        assert hints.read_only_hint is ALL_TOOLS[name], name
        assert hints.destructive_hint is (name in DESTRUCTIVE), name
        assert isinstance(hints.idempotent_hint, bool), name
        assert hints.open_world_hint is False, name
        if hints.read_only_hint:
            assert hints.idempotent_hint is True, name


async def test_every_parameter_is_typed_and_documented(fake):
    for name, tool in (await list_tools(fake)).items():
        schema = tool.input_schema
        assert schema["type"] == "object", name
        for param, spec in schema.get("properties", {}).items():
            assert spec.get("description"), f"{name}.{param} has no description"
            assert "type" in spec or "anyOf" in spec or "enum" in spec or "$ref" in spec, f"{name}.{param}"


def _schema_titles(node):
    """Auto-generated pydantic 'title' annotations anywhere in a schema (not properties named 'title')."""
    if isinstance(node, dict):
        found = [node["title"]] if isinstance(node.get("title"), str) else []
        return found + [t for value in node.values() for t in _schema_titles(value)]
    if isinstance(node, list):
        return [t for value in node for t in _schema_titles(value)]
    return []


async def test_schemas_carry_no_redundant_titles(fake):
    # Pydantic adds a title to every property; it repeats the name and costs ~10% of tools/list.
    tools = await list_tools(fake)

    for name, tool in tools.items():
        assert _schema_titles(tool.input_schema) == [], name
        assert _schema_titles(tool.output_schema) == [], name
    assert "title" in tools["show_title"].input_schema["properties"]  # a parameter *named* title survives


async def test_every_tool_declares_structured_output(fake):
    for name, tool in (await list_tools(fake)).items():
        assert tool.output_schema and tool.output_schema["type"] == "object", name


async def test_read_only_mode_registers_only_non_mutating_tools(fake):
    tools = await list_tools(fake, read_only=True)

    assert set(tools) == READ_ONLY_TOOLS
    assert len(tools) == 21


async def test_allow_and_deny_lists_filter_tools(fake):
    blocks_only = await list_tools(fake, allowed_tools=("group:blocks", "get_players"))
    assert set(blocks_only) == set(CATALOG["blocks"]) | {"get_players"}

    without_commands = await list_tools(fake, denied_tools=("run_command", "kill_*"))
    assert set(without_commands) == set(ALL_TOOLS) - {"run_command", "kill_entities"}


async def test_denied_tools_cannot_be_called(fake):
    async with connect(fake, denied_tools=("run_command",)) as client:
        result = await client.call_tool("run_command", {"command": "stop"})

    assert result.is_error
    assert "Unknown tool" in result.content[0].text
    assert fake.requests == []


async def test_descriptions_state_the_configured_block_limit(fake):
    tools = await list_tools(fake, max_blocks=1234)

    for name in ("fill_region", "get_blocks", "edit_blocks", "build_from_layers", "fill_biome"):
        assert "1,234" in tools[name].description, name


async def test_server_instructions_mention_limits_and_mode(fake):
    async with connect(fake, read_only=True, max_blocks=4321) as client:
        instructions = client.instructions or ""

    assert "4,321" in instructions
    assert "read-only" in instructions.lower()
