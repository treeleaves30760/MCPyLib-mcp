import pytest

from mcpylib_mcp.config import Settings, load_settings
from mcpylib_mcp.errors import ConfigError

TOKEN = "s3cr3t-token-value-0123456789"


def test_defaults_when_only_token_is_set():
    settings = load_settings({"MCPYLIB_TOKEN": TOKEN})

    assert settings.host == "localhost"
    assert settings.port == 65535
    assert settings.token == TOKEN
    assert settings.timeout == 30.0
    assert settings.max_blocks == 100_000
    assert settings.read_only is False
    assert settings.allowed_tools == ()
    assert settings.denied_tools == ()
    assert settings.transport == "stdio"
    assert settings.http_host == "127.0.0.1"
    assert settings.http_port == 8000
    assert settings.log_level == "INFO"


def test_every_environment_variable_is_parsed():
    settings = load_settings(
        {
            "MCPYLIB_HOST": "mc.example.net",
            "MCPYLIB_PORT": "25599",
            "MCPYLIB_TOKEN": TOKEN,
            "MCPYLIB_TIMEOUT": "12.5",
            "MCPYLIB_MAX_BLOCKS": "5000",
            "MCPYLIB_READ_ONLY": "yes",
            "MCPYLIB_ALLOWED_TOOLS": "get_*, group:blocks",
            "MCPYLIB_DENIED_TOOLS": "run_command fill_region",
            "MCPYLIB_TRANSPORT": "http",
            "MCPYLIB_HTTP_HOST": "0.0.0.0",
            "MCPYLIB_HTTP_PORT": "9000",
            "MCPYLIB_LOG_LEVEL": "debug",
        }
    )

    assert settings.host == "mc.example.net"
    assert settings.port == 25599
    assert settings.timeout == 12.5
    assert settings.max_blocks == 5000
    assert settings.read_only is True
    assert settings.allowed_tools == ("get_*", "group:blocks")
    assert settings.denied_tools == ("run_command", "fill_region")
    assert settings.transport == "http"
    assert settings.http_host == "0.0.0.0"
    assert settings.http_port == 9000
    assert settings.log_level == "DEBUG"


def test_overrides_take_precedence_over_environment():
    env = {"MCPYLIB_TOKEN": "from-env", "MCPYLIB_PORT": "1234", "MCPYLIB_READ_ONLY": "true"}

    settings = load_settings(env, {"token": TOKEN, "port": 4321, "read_only": False, "host": None})

    assert settings.token == TOKEN
    assert settings.port == 4321
    assert settings.read_only is False
    assert settings.host == "localhost"  # a None override means "not given"


def test_missing_token_is_a_clear_error():
    with pytest.raises(ConfigError, match="MCPYLIB_TOKEN"):
        load_settings({})


def test_token_can_be_optional_for_offline_commands():
    settings = load_settings({}, require_token=False)

    assert settings.token == ""


def test_token_whitespace_is_stripped():
    settings = load_settings({"MCPYLIB_TOKEN": f"  {TOKEN}\n"})

    assert settings.token == TOKEN


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MCPYLIB_PORT", "abc"),
        ("MCPYLIB_PORT", "0"),
        ("MCPYLIB_PORT", "70000"),
        ("MCPYLIB_TIMEOUT", "-1"),
        ("MCPYLIB_TIMEOUT", "soon"),
        ("MCPYLIB_MAX_BLOCKS", "0"),
        ("MCPYLIB_MAX_BLOCKS", "lots"),
        ("MCPYLIB_READ_ONLY", "maybe"),
        ("MCPYLIB_TRANSPORT", "carrier-pigeon"),
        ("MCPYLIB_HTTP_PORT", "-5"),
        ("MCPYLIB_LOG_LEVEL", "LOUD"),
    ],
)
def test_invalid_values_name_the_offending_variable(name, value):
    with pytest.raises(ConfigError, match=name):
        load_settings({"MCPYLIB_TOKEN": TOKEN, name: value})


def test_streamable_http_is_an_alias_for_http():
    settings = load_settings({"MCPYLIB_TOKEN": TOKEN, "MCPYLIB_TRANSPORT": "streamable-http"})

    assert settings.transport == "http"


def test_lists_accept_commas_and_whitespace():
    settings = load_settings({"MCPYLIB_TOKEN": TOKEN, "MCPYLIB_DENIED_TOOLS": " a, b  c,,d\n"})

    assert settings.denied_tools == ("a", "b", "c", "d")


def test_token_never_appears_in_repr_or_str():
    settings = load_settings({"MCPYLIB_TOKEN": TOKEN})

    assert TOKEN not in repr(settings)
    assert TOKEN not in str(settings)
    assert "***" in repr(settings)


def test_settings_validate_on_direct_construction():
    with pytest.raises(ConfigError, match="max_blocks"):
        Settings(token=TOKEN, max_blocks=0)
