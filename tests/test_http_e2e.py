"""Run ``mcpylib-mcp --transport http`` as a real process and talk to it over streamable HTTP."""

import os
import socket
import subprocess
import sys
import time

import anyio
import pytest
from mcp import Client

pytestmark = pytest.mark.anyio


async def wait_until_listening(port: int, process: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"the server exited early with code {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            await anyio.sleep(0.1)
    raise AssertionError(f"the server did not listen on port {port} within {timeout:g}s")


async def test_http_server_end_to_end(fake, free_port, tmp_path):
    env = os.environ | {
        "MCPYLIB_TOKEN": fake.token,
        "MCPYLIB_HOST": "127.0.0.1",
        "MCPYLIB_PORT": str(fake.port),
        "MCPYLIB_LOG_LEVEL": "DEBUG",  # as much log output as possible, to check it for the token
    }
    command = [sys.executable, "-m", "mcpylib_mcp", "--transport", "http", "--host", "127.0.0.1"]
    log_path = tmp_path / "server.log"
    results = {}

    with log_path.open("wb") as log:
        process = subprocess.Popen([*command, "--port", str(free_port)], env=env, stdout=log, stderr=log)
        try:
            await wait_until_listening(free_port, process)
            for mode in ("legacy", "auto"):
                url = f"http://127.0.0.1:{free_port}/mcp"
                async with Client(url, mode=mode, cache=None, read_timeout_seconds=30) as client:
                    tools = (await client.list_tools()).tools
                    players = await client.call_tool("get_players", {})
                    rejected = await client.call_tool("set_block", {"x": 0, "y": 70, "z": 0, "block": "invalid_x"})
                results[mode] = (len(tools), players.structured_content["online_count"], rejected.is_error)
        finally:
            process.terminate()
            process.wait(timeout=10)

    output = log_path.read_text(encoding="utf-8", errors="replace")
    assert results == {"legacy": (86, 2, True), "auto": (86, 2, True)}, output
    assert "streamable HTTP" in output  # our startup log line went to the captured output
    assert fake.token not in output
