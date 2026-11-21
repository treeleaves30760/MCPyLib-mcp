import logging

import pytest
from helpers import connect
from mcp.server.mcpserver import MCPServer

from mcpylib_mcp import __version__
from mcpylib_mcp.cli import configure_logging, main, parse_settings

TOKEN = "cli-test-token-Hq4wPz9r"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in ("HOST", "PORT", "TOKEN", "TIMEOUT", "MAX_BLOCKS", "READ_ONLY", "ALLOWED_TOOLS", "DENIED_TOOLS",
                 "TRANSPORT", "HTTP_HOST", "HTTP_PORT", "LOG_LEVEL"):  # fmt: skip
        monkeypatch.delenv(f"MCPYLIB_{name}", raising=False)


@pytest.fixture
def restore_logging():
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.fixture
def captured_runs(monkeypatch):
    runs = []
    monkeypatch.setattr(MCPServer, "run", lambda self, transport="stdio", **kwargs: runs.append((transport, kwargs)))
    return runs


def test_help_works_without_a_token(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])

    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--read-only" in out
    assert "MCPYLIB_TOKEN" in out


def test_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])

    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_missing_token_exits_with_guidance(capsys):
    assert main([]) == 2

    err = capsys.readouterr().err
    assert "MCPYLIB_TOKEN" in err
    assert "/mcpylib token" in err


def test_flags_override_environment():
    env = {"MCPYLIB_TOKEN": TOKEN, "MCPYLIB_PORT": "1111", "MCPYLIB_READ_ONLY": "true", "MCPYLIB_HTTP_PORT": "8001"}

    settings, _ = parse_settings(
        ["--mc-port", "2222", "--no-read-only", "--deny-tools", "run_command,kill_entities", "--port", "9002"], env
    )

    assert settings.port == 2222
    assert settings.read_only is False
    assert settings.denied_tools == ("run_command", "kill_entities")
    assert settings.http_port == 9002
    assert settings.token == TOKEN


def test_list_tools_needs_no_token_and_respects_filters(capsys):
    assert main(["--list-tools", "--read-only"]) == 0

    out = capsys.readouterr().out
    assert "21 of 86 tools enabled" in out
    lines = {line.split()[1]: line for line in out.splitlines() if line.startswith(("  +", "  -"))}
    assert lines["get_block"].startswith("  +")
    assert lines["set_block"].startswith("  -")


def test_bad_tool_filter_is_a_startup_error(capsys):
    assert main(["--list-tools", "--deny-tools", "run_comand"]) == 2

    assert "does not match any tool" in capsys.readouterr().err


def test_stdio_is_the_default_transport(monkeypatch, captured_runs, restore_logging):
    monkeypatch.setenv("MCPYLIB_TOKEN", TOKEN)

    assert main([]) == 0
    assert captured_runs == [("stdio", {})]


def test_http_transport_uses_host_and_port(monkeypatch, captured_runs, restore_logging):
    monkeypatch.setenv("MCPYLIB_TOKEN", TOKEN)

    assert main(["--transport", "http", "--host", "127.0.0.1", "--port", "9123"]) == 0
    assert captured_runs == [("streamable-http", {"host": "127.0.0.1", "port": 9123})]


def test_http_on_all_interfaces_warns(monkeypatch, captured_runs, restore_logging, caplog):
    monkeypatch.setenv("MCPYLIB_TOKEN", TOKEN)

    main(["--transport", "http", "--host", "0.0.0.0"])

    assert "without authentication" in caplog.text


def test_log_output_redacts_the_token(capsys, restore_logging):
    configure_logging("INFO", [TOKEN])

    logging.getLogger("mcpylib_mcp.test").warning("accidentally logging %s", TOKEN)

    err = capsys.readouterr().err
    assert TOKEN not in err
    assert "accidentally logging ***" in err


@pytest.mark.anyio
async def test_token_never_reaches_the_logs(fake, caplog):
    caplog.set_level(logging.DEBUG)
    async with connect(fake) as client:
        await client.call_tool("get_players", {})
        await client.call_tool("set_block", {"x": 0, "y": 70, "z": 0, "block": "invalid_block"})
        await client.read_resource("minecraft://server/status")
    async with connect(fake, token=TOKEN) as client:  # rejected by the plugin
        await client.call_tool("get_players", {})

    assert caplog.records, "expected some log output"
    assert fake.token not in caplog.text
    assert TOKEN not in caplog.text
