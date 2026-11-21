"""Run the real ``mcpylib-mcp`` process over stdio, as MCP clients do, against the fake plugin."""

import os
import sys

import pytest
from mcp import Client, StdioServerParameters

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("mode", ["legacy", "auto"])  # legacy = the initialize handshake most clients use today
async def test_stdio_server_end_to_end(fake, mode):
    env = os.environ | {
        "MCPYLIB_TOKEN": fake.token,
        "MCPYLIB_HOST": "127.0.0.1",
        "MCPYLIB_PORT": str(fake.port),
        "MCPYLIB_LOG_LEVEL": "WARNING",
    }
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcpylib_mcp"], env=env)

    async with Client(params, mode=mode, cache=None, read_timeout_seconds=30) as client:
        tools = (await client.list_tools()).tools
        players = await client.call_tool("get_players", {})
        built = await client.call_tool(
            "build_from_layers", {"x": 0, "y": 100, "z": 0, "palette": {"#": "stone"}, "layers": [["##"]]}
        )

    assert len(tools) == 86
    assert players.structured_content["online_count"] == 2
    assert built.structured_content["blocks_placed"] == 2
    assert fake.block_at(1, 100, 0) == "minecraft:stone"
