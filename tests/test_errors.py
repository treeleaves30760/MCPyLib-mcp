"""MCPyLib failures must reach the model as clear tool errors, never as crashes or token leaks."""

import pytest
from helpers import connect, error_text

pytestmark = pytest.mark.anyio


async def test_wrong_token_becomes_an_authentication_error(fake):
    async with connect(fake, token="definitely-the-wrong-token") as client:
        text = error_text(await client.call_tool("get_players", {}))

    assert text.startswith("Error executing tool get_players: Authentication failed")
    assert "MCPYLIB_TOKEN" in text
    assert "definitely-the-wrong-token" not in text
    assert fake.token not in text


async def test_unreachable_plugin_becomes_a_connection_error(fake, free_port):
    async with connect(fake, port=free_port) as client:
        text = error_text(await client.call_tool("get_players", {}))

    assert f"Cannot reach the MCPyLib plugin at 127.0.0.1:{free_port}" in text


async def test_plugin_command_errors_are_passed_through(fake):
    async with connect(fake) as client:
        player = error_text(await client.call_tool("get_player_position", {"username": "Herobrine"}))
        block = error_text(await client.call_tool("set_block", {"x": 0, "y": 70, "z": 0, "block": "invalid_block"}))

    assert player == (
        "Error executing tool get_player_position: The Minecraft server rejected the request: "
        "Player not found: Herobrine"
    )
    assert "Invalid block type: invalid_block" in block


async def test_timeouts_become_tool_errors(fake):
    fake.delay = 1.0
    async with connect(fake, timeout=0.3) as client:
        text = error_text(await client.call_tool("get_players", {}))

    assert "Timed out after 0.3s" in text


async def test_out_of_range_arguments_are_rejected_before_sending(fake):
    async with connect(fake) as client:
        text = error_text(await client.call_tool("set_block", {"x": 0, "y": 5000, "z": 0, "block": "stone"}))

    assert "y" in text
    assert fake.requests == []
