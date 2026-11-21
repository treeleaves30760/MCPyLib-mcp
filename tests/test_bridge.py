import threading

import pytest

from mcpylib_mcp.bridge import MinecraftBridge
from mcpylib_mcp.errors import MinecraftError


def make_bridge(fake, **kwargs):
    options = {"host": "127.0.0.1", "port": fake.port, "token": fake.token, "timeout": 2.0} | kwargs
    return MinecraftBridge(**options)


def test_call_returns_plugin_data(fake):
    bridge = make_bridge(fake)

    assert bridge.call("getblock", 0, 63, 0) == "minecraft:grass_block"
    assert fake.requests[-1] == ("getblock", {"x": 0, "y": 63, "z": 0})
    bridge.close()


def test_wrong_token_is_reported_as_authentication_failure(fake):
    bridge = make_bridge(fake, token="wrong-token-123")

    with pytest.raises(MinecraftError) as excinfo:
        bridge.call("list")

    message = str(excinfo.value)
    assert "Authentication failed" in message
    assert "MCPYLIB_TOKEN" in message
    assert "/mcpylib token" in message
    assert "wrong-token-123" not in message


def test_unreachable_plugin_names_the_target(free_port):
    bridge = MinecraftBridge("127.0.0.1", free_port, "token", timeout=2.0)

    with pytest.raises(MinecraftError) as excinfo:
        bridge.call("list")

    message = str(excinfo.value)
    assert "Cannot reach the MCPyLib plugin" in message
    assert f"127.0.0.1:{free_port}" in message


def test_command_errors_carry_the_plugin_message(fake):
    bridge = make_bridge(fake)

    with pytest.raises(MinecraftError, match="Player not found: Herobrine"):
        bridge.call("getPos", "Herobrine")


def test_timeouts_are_reported_and_the_connection_recovers(fake):
    bridge = make_bridge(fake, timeout=0.3)
    fake.delay = 1.0

    with pytest.raises(MinecraftError, match="Timed out after 0.3s"):
        bridge.call("list")

    fake.delay = 0
    assert bridge.call("list")["online_count"] == 2


def test_non_protocol_responses_are_reported(fake):
    bridge = make_bridge(fake)
    fake.garbage = True

    with pytest.raises(MinecraftError, match="not a valid MCPyLib response"):
        bridge.call("list")


def test_bridge_reconnects_after_the_plugin_restarts(fake):
    bridge = make_bridge(fake)
    assert bridge.call("list")["online_count"] == 2

    port = fake.port
    fake.stop()
    fake.start(port)

    assert bridge.call("list")["online_count"] == 2


def test_concurrent_calls_share_one_connection_safely(fake):
    bridge = make_bridge(fake)
    for x in range(8):
        fake.blocks[(x, 200, 0)] = f"minecraft:block_{x}"
    mismatches: list[tuple[int, str]] = []

    def worker(x: int) -> None:
        for _ in range(25):
            got = bridge.call("getblock", x, 200, 0)
            if got != f"minecraft:block_{x}":
                mismatches.append((x, got))

    threads = [threading.Thread(target=worker, args=(x,)) for x in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert mismatches == []
