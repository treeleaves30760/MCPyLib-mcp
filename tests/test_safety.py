import pytest

from mcpylib_mcp.errors import ConfigError, SafetyLimitError
from mcpylib_mcp.safety import ToolInfo, enforce_block_limit, region_volume, select_tools

CATALOG = [
    ToolInfo("get_block", "blocks", True),
    ToolInfo("set_block", "blocks", False),
    ToolInfo("fill_region", "blocks", False),
    ToolInfo("get_players", "server", True),
    ToolInfo("run_command", "server", False),
    ToolInfo("teleport_player", "players", False),
]


@pytest.mark.parametrize(
    ("corners", "expected"),
    [
        ((0, 0, 0, 0, 0, 0), 1),
        ((0, 0, 0, 9, 9, 9), 1000),
        ((9, 9, 9, 0, 0, 0), 1000),
        ((-5, 64, 3, 5, 64, -3), 11 * 1 * 7),
    ],
)
def test_region_volume_is_inclusive_and_order_independent(corners, expected):
    assert region_volume(*corners) == expected


def test_block_limit_allows_exactly_the_limit():
    enforce_block_limit(100, 100, "fill_region")


def test_block_limit_error_explains_how_to_proceed():
    with pytest.raises(SafetyLimitError) as excinfo:
        enforce_block_limit(250_000, 100_000, "This fill")

    message = str(excinfo.value)
    assert "250,000" in message
    assert "100,000" in message
    assert "MCPYLIB_MAX_BLOCKS" in message


def test_all_tools_selected_by_default():
    assert select_tools(CATALOG, read_only=False, allowed=(), denied=()) == [t.name for t in CATALOG]


def test_read_only_keeps_only_non_mutating_tools():
    assert select_tools(CATALOG, read_only=True, allowed=(), denied=()) == ["get_block", "get_players"]


def test_allowlist_accepts_names_globs_and_groups():
    selected = select_tools(
        CATALOG, read_only=False, allowed=("run_command", "get_*", "group:players"), denied=()
    )

    assert selected == ["get_block", "get_players", "run_command", "teleport_player"]


def test_denylist_wins_over_allowlist():
    selected = select_tools(CATALOG, read_only=False, allowed=("group:blocks",), denied=("set_*",))

    assert selected == ["get_block", "fill_region"]


def test_read_only_cannot_be_widened_by_allowlist():
    assert select_tools(CATALOG, read_only=True, allowed=("set_block", "get_block"), denied=()) == [
        "get_block"
    ]


@pytest.mark.parametrize("entry", ["run_comand", "group:nope", "zzz_*"])
def test_entries_that_match_nothing_are_rejected(entry):
    # A typo in a denylist must not silently leave a dangerous tool enabled.
    with pytest.raises(ConfigError, match="MCPYLIB_DENIED_TOOLS"):
        select_tools(CATALOG, read_only=False, allowed=(), denied=(entry,))
    with pytest.raises(ConfigError, match="MCPYLIB_ALLOWED_TOOLS"):
        select_tools(CATALOG, read_only=False, allowed=(entry,), denied=())
