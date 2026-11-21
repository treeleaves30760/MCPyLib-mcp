import json

import pytest
from helpers import connect, error_text, ok_data

pytestmark = pytest.mark.anyio

STEVE = "Steve"


# ---------------------------------------------------------------- server
async def test_get_players(fake):
    async with connect(fake) as client:
        data = ok_data(await client.call_tool("get_players", {}))

    assert data["online_count"] == 2
    assert {p["name"] for p in data["players"]} == {"Steve", "Alex"}


async def test_run_command_reports_dispatch(fake):
    async with connect(fake) as client:
        data = ok_data(await client.call_tool("run_command", {"command": "/say hi"}))

    assert data == {"command": "/say hi", "dispatched": True}
    assert fake.last("exec") == {"command": "/say hi"}


async def test_run_command_rejects_multi_line_input(fake):
    async with connect(fake) as client:
        result = await client.call_tool("run_command", {"command": "say hi\nstop"})

    assert result.is_error
    assert fake.requests == []


# ---------------------------------------------------------------- players
async def test_player_position_and_teleport_with_rotation(fake):
    async with connect(fake) as client:
        position = ok_data(await client.call_tool("get_player_position", {"username": STEVE}))
        ok_data(
            await client.call_tool(
                "teleport_player", {"username": STEVE, "x": 0.5, "y": 70, "z": 0.5, "yaw": 90, "pitch": 0}
            )
        )

    assert position == {"username": STEVE, "x": 10, "y": 64, "z": -20}
    assert fake.last("teleport") == {
        "username": STEVE,
        "x": 0.5,
        "y": 70.0,
        "z": 0.5,
        "yaw": 90.0,
        "pitch": 0.0,
    }


async def test_yaw_and_pitch_must_be_given_together(fake):
    async with connect(fake) as client:
        text = error_text(
            await client.call_tool("teleport_player", {"username": STEVE, "x": 0, "y": 70, "z": 0, "yaw": 90})
        )

    assert "yaw and pitch" in text
    assert fake.requests == []


async def test_give_item_validates_amount_locally(fake):
    async with connect(fake) as client:
        result = await client.call_tool("give_item", {"username": STEVE, "item": "diamond", "amount": 65})

    assert result.is_error
    assert "amount" in result.content[0].text
    assert fake.requests == []


async def test_get_inventory_lists_non_empty_slots(fake):
    async with connect(fake) as client:
        everything = ok_data(await client.call_tool("get_inventory", {"username": STEVE}))
        one = ok_data(await client.call_tool("get_inventory", {"username": STEVE, "slots": [3]}))

    assert everything["slots_checked"] == 41
    assert [item["slot"] for item in everything["items"]] == [0, 3]
    assert everything["items"][0]["enchantments"] == {"sharpness": 5}
    assert one["items"] == [{"slot": 3, "item": "minecraft:bread", "amount": 12}]


async def test_experience_query_and_update(fake):
    async with connect(fake) as client:
        before = ok_data(await client.call_tool("get_experience", {"username": STEVE}))
        after = ok_data(
            await client.call_tool(
                "update_experience", {"username": STEVE, "amount": 3, "mode": "add", "unit": "levels"}
            )
        )

    assert before["level"] == 5
    assert after["level"] == 8
    assert fake.last("experience") == {"username": STEVE, "action": "add", "amount": 3, "target": "levels"}


async def test_spawnpoint_coordinates_are_all_or_nothing(fake):
    async with connect(fake) as client:
        text = error_text(await client.call_tool("set_spawnpoint", {"username": STEVE, "x": 1, "y": 2}))

    assert "x, y and z" in text
    assert fake.requests == []


async def test_advancements(fake):
    async with connect(fake) as client:
        ok_data(
            await client.call_tool(
                "set_advancement", {"username": STEVE, "advancement": "story/mine_stone", "granted": True}
            )
        )
        data = ok_data(
            await client.call_tool("get_advancement", {"username": STEVE, "advancement": "story/mine_stone"})
        )

    assert data["done"] is True


async def test_spread_players_checks_range(fake):
    async with connect(fake) as client:
        text = error_text(
            await client.call_tool(
                "spread_players",
                {"usernames": [STEVE], "center_x": 0, "center_z": 0, "spread_distance": 10, "max_range": 10},
            )
        )

    assert "max_range" in text
    assert fake.requests == []


# ---------------------------------------------------------------- world
async def test_time_presets_and_description(fake):
    async with connect(fake) as client:
        now = ok_data(await client.call_tool("get_time", {}))
        noon = ok_data(await client.call_tool("set_time", {"value": "noon"}))
        error = error_text(await client.call_tool("set_time", {"value": "night", "mode": "add"}))

    assert now == {"time": 1000, "phase": "day", "clock": "07:00"}
    assert noon == {"time": 6000, "phase": "day", "clock": "12:00"}
    assert fake.last("time") == {"action": "set", "value": 6000}
    assert "preset" in error


async def test_set_gamerule_converts_booleans(fake):
    async with connect(fake) as client:
        data = ok_data(await client.call_tool("set_gamerule", {"rule": "keep_inventory", "value": True}))

    assert data == {"rule": "keep_inventory", "value": "true"}
    assert fake.last("gamerule") == {"rule": "keep_inventory", "value": "true"}


async def test_set_world_border_issues_only_the_needed_calls(fake):
    async with connect(fake) as client:
        data = ok_data(
            await client.call_tool(
                "set_world_border",
                {
                    "size": 1000,
                    "transition_seconds": 10,
                    "center_x": 5,
                    "center_z": -5,
                    "warning_distance": 3,
                },
            )
        )

    border_calls = [params for action, params in fake.requests if action == "worldborder"]
    assert border_calls == [
        {"action": "center", "x": 5.0, "z": -5.0},
        {"action": "set", "value": 1000.0, "time": 10},
        {"action": "warning", "value": 3},
        {"action": "get"},
    ]
    assert data["border"]["size"] == 1000.0
    assert data["border"]["center_x"] == 5.0


async def test_set_world_border_needs_a_change(fake):
    async with connect(fake) as client:
        text = error_text(await client.call_tool("set_world_border", {}))

    assert "at least one" in text


async def test_chunk_force_loading_uses_chunk_of_block(fake):
    async with connect(fake) as client:
        ok_data(await client.call_tool("set_chunk_force_loaded", {"x": 33, "z": -1, "force_loaded": True}))
        data = ok_data(await client.call_tool("get_chunk_force_loaded", {"x": 40, "z": -16}))

    assert data == {"x": 40, "z": -16, "chunk_x": 2, "chunk_z": -1, "force_loaded": True}


async def test_locate_structure(fake):
    async with connect(fake) as client:
        found = ok_data(await client.call_tool("locate_structure", {"structure": "village_plains"}))
        missing = ok_data(await client.call_tool("locate_structure", {"structure": "unicorn_castle", "x": 0, "z": 0}))

    assert found == {"structure": "village_plains", "found": True, "x": 256, "y": 64, "z": -128}
    assert missing == {"structure": "unicorn_castle", "found": False}


async def test_place_template_forwards_every_option(fake):
    async with connect(fake) as client:
        ok_data(
            await client.call_tool(
                "place_template",
                {
                    "template": "minecraft:igloo/top",
                    "x": 1,
                    "y": 70,
                    "z": 2,
                    "rotation": "clockwise_90",
                    "integrity": 0.5,
                },
            )
        )

    assert fake.last("placeTemplate") == {
        "template": "minecraft:igloo/top",
        "rotation": "clockwise_90",
        "mirror": "none",
        "integrity": 0.5,
        "seed": 0,
        "x": 1,
        "y": 70,
        "z": 2,
    }


async def test_command_style_ids_cannot_inject_arguments(fake):
    async with connect(fake) as client:
        result = await client.call_tool(
            "fill_biome",
            {
                "x1": 0,
                "y1": 0,
                "z1": 0,
                "x2": 1,
                "y2": 1,
                "z2": 1,
                "biome": "minecraft:plains replace minecraft:ocean",
            },
        )

    assert result.is_error
    assert fake.requests == []


# ---------------------------------------------------------------- entities
async def test_entity_lifecycle(fake):
    async with connect(fake) as client:
        summoned = ok_data(
            await client.call_tool("summon_entity", {"entity_type": "zombie", "x": 1.5, "y": 64, "z": 1.5})
        )
        entity = ok_data(await client.call_tool("get_entity", {"uuid": summoned["uuid"]}))
        ok_data(await client.call_tool("remove_entity", {"uuid": summoned["uuid"]}))
        gone = error_text(await client.call_tool("get_entity", {"uuid": summoned["uuid"]}))

    assert entity["type"] == "minecraft:zombie"
    assert entity["rotation"] == {"yaw": 0.0, "pitch": 0.0}
    assert "Entity not found" in gone


async def test_kill_entities_by_type(fake):
    async with connect(fake) as client:
        for entity_type in ("zombie", "zombie", "pig"):
            ok_data(await client.call_tool("summon_entity", {"entity_type": entity_type, "x": 0, "y": 64, "z": 0}))
        data = ok_data(await client.call_tool("kill_entities", {"target": "zombie"}))

    assert data == {"target": "zombie", "count": 2}
    assert [e["type"] for e in fake.entities.values()] == ["minecraft:pig"]


async def test_update_entity_tags(fake):
    async with connect(fake) as client:
        uuid = ok_data(await client.call_tool("summon_entity", {"entity_type": "pig", "x": 0, "y": 64, "z": 0}))["uuid"]
        data = ok_data(
            await client.call_tool("update_entity_tags", {"uuid": uuid, "add": ["boss", "red"], "remove": ["red"]})
        )

    assert data["tags"] == ["boss"]
    assert data["added"] == ["boss", "red"]
    assert data["removed"] == ["red"]


async def test_malformed_uuid_is_rejected_locally(fake):
    async with connect(fake) as client:
        result = await client.call_tool("get_entity", {"uuid": "not-a-uuid"})

    assert result.is_error
    assert fake.requests == []


async def test_set_entity_equipment_builds_slot_map(fake):
    uuid = "8667ba71-b85a-4004-af54-457a9734eed8"
    async with connect(fake) as client:
        ok_data(
            await client.call_tool(
                "set_entity_equipment",
                {
                    "uuid": uuid,
                    "helmet": "iron_helmet",
                    "main_hand": "iron_sword",
                    "drop_chances": {"main_hand": 0.5},
                },
            )
        )

    assert fake.last("setEntityEquipment") == {
        "uuid": uuid,
        "equipment": {"helmet": "iron_helmet", "main_hand": "iron_sword"},
        "drop_chances": {"main_hand": 0.5},
    }


async def test_set_villager_trades_serializes_trades(fake):
    uuid = "8667ba71-b85a-4004-af54-457a9734eed9"
    trades = [
        {"buy1": {"item": "emerald", "amount": 5}, "sell": {"item": "diamond_sword"}, "max_uses": 3},
        {"buy1": {"item": "emerald"}, "buy2": {"item": "book"}, "sell": {"item": "enchanted_book"}},
    ]
    async with connect(fake) as client:
        ok_data(await client.call_tool("set_villager_trades", {"uuid": uuid, "trades": trades}))

    assert fake.last("setVillagerTrades")["trades"] == [
        {
            "buy1": {"item": "emerald", "amount": 5},
            "sell": {"item": "diamond_sword", "amount": 1},
            "max_uses": 3,
            "experience_reward": True,
        },
        {
            "buy1": {"item": "emerald", "amount": 1},
            "buy2": {"item": "book", "amount": 1},
            "sell": {"item": "enchanted_book", "amount": 1},
            "max_uses": 10,
            "experience_reward": True,
        },
    ]


# ---------------------------------------------------------------- chat
async def test_send_rich_message_accepts_components_and_plain_text(fake):
    async with connect(fake) as client:
        ok_data(await client.call_tool("send_rich_message", {"target": "@a", "text": {"text": "Hi", "color": "gold"}}))
        component = json.loads(fake.last("tellraw")["json_text"])
        ok_data(await client.call_tool("send_rich_message", {"target": STEVE, "text": "plain words"}))
        plain = json.loads(fake.last("tellraw")["json_text"])

    assert component == {"text": "Hi", "color": "gold"}
    assert plain == {"text": "plain words"}


async def test_send_rich_message_rejects_spaces_in_target(fake):
    async with connect(fake) as client:
        result = await client.call_tool("send_rich_message", {"target": "@a[tag=x, distance=..5]", "text": "hi"})

    assert result.is_error
    assert fake.requests == []


async def test_show_title_needs_text(fake):
    async with connect(fake) as client:
        text = error_text(await client.call_tool("show_title", {"username": STEVE}))

    assert "title or subtitle" in text


async def test_stop_sound_source_requires_sound(fake):
    async with connect(fake) as client:
        text = error_text(await client.call_tool("stop_sound", {"username": STEVE, "source": "music"}))

    assert "source" in text
    assert fake.requests == []


# ---------------------------------------------------------------- scoreboard
async def test_scores(fake):
    async with connect(fake) as client:
        ok_data(await client.call_tool("create_objective", {"name": "kills", "display_name": "Kills"}))
        ok_data(await client.call_tool("set_score", {"objective": "kills", "player": STEVE, "score": 7}))
        data = ok_data(await client.call_tool("get_score", {"objective": "kills", "player": STEVE}))

    assert fake.last("addObjective") == {"name": "kills", "criteria": "dummy", "display_name": "Kills"}
    assert data == {"objective": "kills", "player": STEVE, "score": 7}


async def test_team_lifecycle(fake):
    async with connect(fake) as client:
        ok_data(await client.call_tool("create_team", {"name": "red", "display_name": "Red Team"}))
        ok_data(
            await client.call_tool("update_team_members", {"name": "red", "add": [STEVE, "Alex"], "remove": ["Alex"]})
        )
        ok_data(await client.call_tool("set_team_option", {"name": "red", "option": "friendlyfire", "value": False}))
        teams = ok_data(await client.call_tool("list_teams", {}))

    assert teams["teams"] == [{"name": "red", "display_name": "Red Team", "members": [STEVE], "size": 1}]
    assert fake.teams["red"]["options"] == {"friendlyfire": "false"}


async def test_bossbar_lifecycle(fake):
    async with connect(fake) as client:
        created = ok_data(
            await client.call_tool(
                "create_bossbar", {"bar_id": "raid", "title": "Raid", "color": "red", "players": [STEVE]}
            )
        )
        ok_data(await client.call_tool("update_bossbar", {"bar_id": "raid", "progress": 0.5}))
        listed = ok_data(await client.call_tool("list_bossbars", {}))
        ok_data(await client.call_tool("remove_bossbar", {"bar_id": "raid"}))

    assert created["bossbar"]["players"] == [STEVE]
    assert fake.last("bossbar") == {"action": "remove", "id": "raid"}
    assert listed["bossbars"][0]["progress"] == 0.5
    assert listed["bossbars"][0]["color"] == "RED"
    assert fake.bossbars == {}
