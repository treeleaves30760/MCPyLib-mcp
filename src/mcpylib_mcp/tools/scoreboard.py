"""Scoreboard objectives and scores, teams, and boss bars."""

from typing import Annotated, Any, Literal

from pydantic import Field

from ..errors import InvalidInputError
from ..params import Username
from ..registry import ToolRegistry, ToolResult, ok

GROUP = "scoreboard"

ObjectiveName = Annotated[
    str, Field(min_length=1, max_length=64, pattern=r"^\S+$", description="Objective name (no spaces).")
]
OptObjectiveName = Annotated[
    str | None,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^\S+$",
        description="Objective to show; omit to clear the slot.",
    ),
]
TeamName = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^\S+$", description="Team name (no spaces).")]
BarId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^\S+$", description="Boss bar id (no spaces).")]
ScoreHolder = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^\S+$",
        description="Score holder: a player name or any label like '#timer'.",
    ),
]
DisplayName = Annotated[
    str | None, Field(max_length=256, description="Name shown to players; default: the internal name.")
]
BarColor = Literal["pink", "blue", "red", "green", "yellow", "purple", "white"]
BarStyle = Literal["solid", "segmented_6", "segmented_10", "segmented_12", "segmented_20"]
Members = Annotated[list[ScoreHolder] | None, Field(max_length=100, description="Player names (or other entries).")]
Players = Annotated[list[Username] | None, Field(max_length=100, description="Online player names.")]


def register(reg: ToolRegistry) -> None:
    bridge = reg.bridge

    # ------------------------------------------------------------ objectives and scores
    @reg.tool(GROUP, "Create objective")
    def create_objective(
        name: ObjectiveName,
        criteria: Annotated[
            str,
            Field(
                min_length=1,
                max_length=128,
                pattern=r"^\S+$",
                description=(
                    "What the score tracks: 'dummy' (changed only by commands), 'playerKillCount', "
                    "'deathCount', 'health', ..."
                ),
            ),
        ] = "dummy",
        display_name: DisplayName = None,
    ) -> ToolResult:
        """Create a scoreboard objective (fails if it already exists)."""
        bridge.call("addObjective", name, criteria, display_name)
        return ok({"name": name, "criteria": criteria, "display_name": display_name or name})

    @reg.tool(GROUP, "Remove objective", destructive=True, idempotent=True)
    def remove_objective(name: ObjectiveName) -> ToolResult:
        """Delete a scoreboard objective and all of its scores."""
        bridge.call("removeObjective", name)
        return ok({"name": name, "removed": True})

    @reg.tool(GROUP, "Show objective", idempotent=True)
    def set_objective_display(
        slot: Annotated[
            Literal["sidebar", "below_name", "player_list"],
            Field(description="Where on screen to show the objective."),
        ],
        objective: OptObjectiveName = None,
    ) -> ToolResult:
        """Show an objective in the sidebar, below player names or in the player list, or clear that slot."""
        bridge.call("setDisplaySlot", slot, objective)
        return ok({"slot": slot, "objective": objective})

    @reg.tool(GROUP, "Set score", destructive=True, idempotent=True)
    def set_score(
        objective: ObjectiveName,
        player: ScoreHolder,
        score: Annotated[int, Field(ge=-(2**31), le=2**31 - 1, description="New score.")],
    ) -> ToolResult:
        """Set a score holder's score on an objective, replacing the previous value."""
        bridge.call("setScore", objective, player, score)
        return ok({"objective": objective, "player": player, "score": score})

    @reg.tool(GROUP, "Get score", read_only=True)
    def get_score(objective: ObjectiveName, player: ScoreHolder) -> ToolResult:
        """A score holder's score on an objective (0 if they have none)."""
        return ok({"objective": objective, "player": player, "score": bridge.call("getScore", objective, player)})

    # ------------------------------------------------------------ teams
    @reg.tool(GROUP, "List teams", read_only=True)
    def list_teams() -> ToolResult:
        """All scoreboard teams with their display names and members."""
        return ok(bridge.call("team", "list"))

    @reg.tool(GROUP, "Create team")
    def create_team(name: TeamName, display_name: DisplayName = None) -> ToolResult:
        """Create a scoreboard team (fails if it already exists)."""
        bridge.call("team", "add", name, display_name=display_name)
        return ok({"name": name, "display_name": display_name or name})

    @reg.tool(GROUP, "Remove team", destructive=True, idempotent=True)
    def remove_team(name: TeamName) -> ToolResult:
        """Delete a scoreboard team; its members become teamless."""
        bridge.call("team", "remove", name)
        return ok({"name": name, "removed": True})

    @reg.tool(GROUP, "Change team members", idempotent=True)
    def update_team_members(name: TeamName, add: Members = None, remove: Members = None) -> ToolResult:
        """Add and/or remove team members (a player can only be in one team; joining moves them)."""
        if not add and not remove:
            raise InvalidInputError("Give members to add and/or remove.")
        if add:
            bridge.call("team", "join", name, members=add)
        if remove:
            bridge.call("team", "leave", name, members=remove)
        return ok({"name": name, "added": add or [], "removed": remove or []})

    @reg.tool(GROUP, "Set team option", idempotent=True)
    def set_team_option(
        name: TeamName,
        option: Annotated[
            Literal["displayname", "color", "friendlyfire", "seefriendlyinvisibles", "prefix", "suffix"],
            Field(description="Setting to change."),
        ],
        value: Annotated[
            Annotated[str, Field(max_length=256)] | bool,
            Field(
                description=(
                    "New value: true/false for friendlyfire and seefriendlyinvisibles; a colour name (red, blue, gold, "
                    "dark_green, aqua, light_purple, ...) for color; text for displayname, prefix and suffix."
                ),
            ),
        ],
    ) -> ToolResult:
        """Change a team setting such as its colour or friendly fire."""
        text = str(value).lower() if isinstance(value, bool) else value
        bridge.call("team", "modify", name, option=option, value=text)
        return ok({"name": name, "option": option, "value": text})

    # ------------------------------------------------------------ boss bars
    def _bar(bar_id: str) -> dict[str, Any]:
        return bridge.call("bossbar", "get", bar_id)

    @reg.tool(GROUP, "List boss bars", read_only=True)
    def list_bossbars() -> ToolResult:
        """Boss bars created through MCPyLib, with title, colour, style, progress, visibility and viewers."""
        ids = bridge.call("bossbar", "list", "").get("bars", [])
        return ok({"bossbars": [_bar(bar_id) for bar_id in ids]})

    @reg.tool(GROUP, "Create boss bar")
    def create_bossbar(
        bar_id: BarId,
        title: Annotated[
            str | None, Field(max_length=256, description="Text shown above the bar; default: the id.")
        ] = None,
        color: Annotated[BarColor | None, Field(description="Bar colour; default white.")] = None,
        style: Annotated[BarStyle | None, Field(description="Solid or segmented; default solid.")] = None,
        progress: Annotated[float | None, Field(ge=0, le=1, description="Fill level 0-1; default 1.")] = None,
        visible: Annotated[bool | None, Field(description="Whether the bar is shown; default true.")] = None,
        players: Players = None,
    ) -> ToolResult:
        """Create a boss bar and show it to the given players. Bars live in the plugin's memory: they are
        separate from vanilla /bossbar and disappear when the server restarts."""
        bridge.call(
            "bossbar",
            "add",
            bar_id,
            title=title,
            color=color and color.upper(),
            style=style and style.upper(),
            progress=progress,
            visible=visible,
        )
        for username in players or ():
            bridge.call("bossbar", "addplayer", bar_id, username=username)
        return ok({"bossbar": _bar(bar_id)})

    @reg.tool(GROUP, "Update boss bar", idempotent=True)
    def update_bossbar(
        bar_id: BarId,
        title: Annotated[str | None, Field(max_length=256, description="New title.")] = None,
        color: Annotated[BarColor | None, Field(description="New colour.")] = None,
        style: Annotated[BarStyle | None, Field(description="New style.")] = None,
        progress: Annotated[float | None, Field(ge=0, le=1, description="New fill level 0-1.")] = None,
        visible: Annotated[bool | None, Field(description="Show or hide the bar.")] = None,
        add_players: Players = None,
        remove_players: Players = None,
    ) -> ToolResult:
        """Change a boss bar's look or progress and who sees it; omitted settings are left alone."""
        changes = {
            "title": title,
            "color": color and color.upper(),
            "style": style and style.upper(),
            "progress": progress,
            "visible": visible,
        }
        if not any(v is not None for v in changes.values()) and not add_players and not remove_players:
            raise InvalidInputError("Give at least one setting or player change.")
        if any(v is not None for v in changes.values()):
            bridge.call("bossbar", "set", bar_id, **changes)
        for username in add_players or ():
            bridge.call("bossbar", "addplayer", bar_id, username=username)
        for username in remove_players or ():
            bridge.call("bossbar", "removeplayer", bar_id, username=username)
        return ok({"bossbar": _bar(bar_id)})

    @reg.tool(GROUP, "Remove boss bar", destructive=True, idempotent=True)
    def remove_bossbar(bar_id: BarId) -> ToolResult:
        """Delete a boss bar and hide it from everyone."""
        bridge.call("bossbar", "remove", bar_id)
        return ok({"bar_id": bar_id, "removed": True})
