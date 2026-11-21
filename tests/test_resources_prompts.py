import json

import pytest
from helpers import connect
from mcp import MCPError

pytestmark = pytest.mark.anyio


async def read_json(client, uri):
    result = await client.read_resource(uri)
    return json.loads(result.contents[0].text)


async def test_resources_and_templates_are_listed(fake):
    async with connect(fake) as client:
        resources = {str(r.uri): r for r in (await client.list_resources()).resources}
        templates = {t.uri_template: t for t in (await client.list_resource_templates()).resource_templates}

    assert set(resources) == {"minecraft://server/status", "minecraft://guide/building"}
    assert resources["minecraft://server/status"].mime_type == "application/json"
    assert set(templates) == {"minecraft://players/{username}"}
    assert all(r.description for r in resources.values())


async def test_status_resource_summarizes_the_server(fake):
    async with connect(fake, max_blocks=5000, read_only=True) as client:
        status = await read_json(client, "minecraft://server/status")

    assert status["connected"] is True
    assert status["players"]["online_count"] == 2
    assert status["time"]["phase"] == "day"
    assert status["world_border"]["size"] == 60_000_000.0
    assert status["mcp"] == {"read_only": True, "max_blocks": 5000, "tools_enabled": 21}
    assert fake.token not in json.dumps(status)


async def test_status_resource_reports_an_unreachable_plugin_instead_of_failing(fake, free_port):
    async with connect(fake, port=free_port) as client:
        status = await read_json(client, "minecraft://server/status")

    assert status["connected"] is False
    assert "Cannot reach the MCPyLib plugin" in status["error"]


async def test_player_resource(fake):
    async with connect(fake) as client:
        steve = await read_json(client, "minecraft://players/Steve")

    assert steve == {
        "name": "Steve",
        "uuid": "8667ba71-b85a-4004-af54-457a9734eed7",
        "gamemode": "SURVIVAL",
        "position": {"x": 10, "y": 64, "z": -20},
        "experience": {"level": 5, "points": 120, "progress": 0.25},
    }


async def test_player_resource_for_an_offline_player_is_an_error(fake):
    async with connect(fake) as client:
        with pytest.raises(MCPError, match="Player not found: Ghost"):
            await client.read_resource("minecraft://players/Ghost")


async def test_building_guide_explains_conventions_and_limits(fake):
    async with connect(fake, max_blocks=2500) as client:
        guide = (await client.read_resource("minecraft://guide/building")).contents[0].text

    assert "build_from_layers" in guide
    assert "+X" in guide and "+Z" in guide
    assert "2,500" in guide


async def test_prompts_are_listed_with_arguments(fake):
    async with connect(fake) as client:
        prompts = {p.name: p for p in (await client.list_prompts()).prompts}

    assert set(prompts) == {"build_structure", "survey_area"}
    build_args = {a.name: a.required for a in prompts["build_structure"].arguments}
    assert build_args == {"description": True, "location": False}
    assert all(p.description for p in prompts.values())


async def test_build_structure_prompt_contains_the_plan(fake):
    async with connect(fake, max_blocks=7777) as client:
        result = await client.get_prompt("build_structure", {"description": "a lighthouse", "location": "near Steve"})

    text = result.messages[0].content.text
    assert "a lighthouse" in text
    assert "near Steve" in text
    for tool in ("get_height_map", "fill_region", "build_from_layers", "get_blocks"):
        assert tool in text
    assert "7,777" in text


async def test_survey_area_prompt(fake):
    async with connect(fake) as client:
        result = await client.get_prompt("survey_area", {"location": "100 64 -200", "radius": "24"})

    text = result.messages[0].content.text
    assert "100 64 -200" in text
    assert "24" in text
    assert "get_height_map" in text


async def test_build_prompt_is_hidden_in_read_only_mode(fake):
    async with connect(fake, read_only=True) as client:
        prompts = {p.name for p in (await client.list_prompts()).prompts}

    assert prompts == {"survey_area"}
