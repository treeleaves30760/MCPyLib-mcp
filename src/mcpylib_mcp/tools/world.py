"""World tools: time, weather, rules, spawn, world border, chunks, biomes, structures, loot."""

from typing import Annotated, Any, Literal

from pydantic import Field

from ..errors import InvalidInputError
from ..params import (
    X1,
    X2,
    XZ_LIMIT,
    Y1,
    Y2,
    Z1,
    Z2,
    GameMode,
    OptX,
    OptY,
    OptZ,
    PosX,
    PosY,
    PosZ,
    X,
    Y,
    Z,
    all_or_none,
    box,
    resource_id,
)
from ..registry import ToolRegistry, ToolResult, ok
from ..safety import enforce_block_limit, region_volume

GROUP = "world"
TIME_PRESETS = {
    "day": 1000,
    "noon": 6000,
    "sunset": 12000,
    "night": 13000,
    "midnight": 18000,
    "sunrise": 23000,
}

BiomeId = resource_id("Biome id such as 'minecraft:plains', 'desert' or 'cherry_grove'.")
StructureId = resource_id("Structure id such as 'village_plains', 'minecraft:stronghold' or 'ancient_city'.")
FeatureId = resource_id("Configured feature id such as 'minecraft:oak', 'fancy_oak' or 'monster_room'.")
TemplateId = resource_id("Structure template id such as 'minecraft:igloo/top' or a saved structure 'mymap:house'.")
PoolId = resource_id("Jigsaw template pool such as 'minecraft:village/plains/town_centers'.")
LootTableId = resource_id("Loot table id such as 'chests/simple_dungeon' or 'minecraft:entities/zombie'.")
JigsawTarget = resource_id("Name of the jigsaw block to start from, e.g. 'minecraft:bottom'.")
GameRuleId = resource_id(
    "Game rule such as 'keep_inventory' or 'mob_griefing' (legacy names like keepInventory work too)."
)


def describe_time(ticks: int) -> dict[str, Any]:
    """Day time in ticks plus a phase label and a 24h clock (tick 0 = 06:00)."""
    if ticks < 12000:
        phase = "day"
    elif ticks < 13000:
        phase = "sunset"
    elif ticks < 23000:
        phase = "night"
    else:
        phase = "sunrise"
    hours = (ticks // 1000 + 6) % 24
    minutes = (ticks % 1000) * 60 // 1000
    return {"time": ticks, "phase": phase, "clock": f"{hours:02d}:{minutes:02d}"}


def register(reg: ToolRegistry) -> None:
    bridge, limit = reg.bridge, reg.settings.max_blocks

    @reg.tool(GROUP, "Get time of day", read_only=True)
    def get_time() -> ToolResult:
        """Current time of day in the main world: ticks (0-23999), phase (day/sunset/night/sunrise) and clock."""
        return ok(describe_time(bridge.call("time", "query")))

    @reg.tool(GROUP, "Set time of day")
    def set_time(
        value: Annotated[
            int | Literal["day", "noon", "sunset", "night", "midnight", "sunrise"],
            Field(
                description=(
                    "Ticks (20 per second, 24000 per day; 0-24000 when mode is 'set') or a preset: day=1000, "
                    "noon=6000, sunset=12000, night=13000, midnight=18000, sunrise=23000."
                )
            ),
        ],
        mode: Annotated[
            Literal["set", "add"], Field(description="Set the time, or advance it by value ticks.")
        ] = "set",
    ) -> ToolResult:
        """Set or advance the time of day in the main world."""
        if isinstance(value, str):
            if mode == "add":
                raise InvalidInputError("Time presets only work with mode='set'; give a number of ticks to add.")
            value = TIME_PRESETS[value]
        if mode == "set" and not 0 <= value <= 24000:
            raise InvalidInputError("With mode='set' the time must be between 0 and 24000 ticks.")
        if not -1_000_000 <= value <= 1_000_000:
            raise InvalidInputError("value must be between -1,000,000 and 1,000,000 ticks.")
        return ok(describe_time(bridge.call("time", mode, value)))

    @reg.tool(GROUP, "Set weather", idempotent=True)
    def set_weather(
        condition: Annotated[Literal["clear", "rain", "thunder"], Field(description="New weather.")],
        duration_seconds: Annotated[
            int | None,
            Field(ge=1, le=1_000_000, description="How long it lasts; default: the server decides."),
        ] = None,
    ) -> ToolResult:
        """Change the weather in the main world to clear, rain or thunder, optionally for a set duration."""
        bridge.call("weather", condition, duration_seconds)
        return ok({"weather": condition, "duration_seconds": duration_seconds})

    @reg.tool(GROUP, "Set difficulty", idempotent=True)
    def set_difficulty(
        level: Annotated[Literal["peaceful", "easy", "normal", "hard"], Field(description="New difficulty.")],
    ) -> ToolResult:
        """Change the difficulty of the main world. 'peaceful' removes hostile mobs."""
        bridge.call("difficulty", level)
        return ok({"difficulty": level})

    @reg.tool(GROUP, "Get game rule", read_only=True)
    def get_gamerule(rule: GameRuleId) -> ToolResult:
        """Current value of a game rule in the main world, as a string."""
        return ok({"rule": rule, "value": bridge.call("gamerule", rule)})

    @reg.tool(GROUP, "Set game rule", idempotent=True)
    def set_gamerule(
        rule: GameRuleId,
        value: Annotated[
            bool | int | str, Field(description="New value: true/false for switches, a number for counts.")
        ],
    ) -> ToolResult:
        """Set a boolean or integer game rule in the main world and return the value the server now reports
        (check it: the plugin silently ignores values it cannot parse)."""
        text = str(value).lower() if isinstance(value, bool) else str(value)
        return ok({"rule": rule, "value": bridge.call("gamerule", rule, text)})

    @reg.tool(GROUP, "Set world spawn", idempotent=True)
    def set_world_spawn(x: X, y: Y, z: Z) -> ToolResult:
        """Set the main world's spawn point (where new players appear and compasses point)."""
        bridge.call("setworldspawn", x, y, z)
        return ok({"x": x, "y": y, "z": z})

    @reg.tool(GROUP, "Set default game mode", idempotent=True)
    def set_default_gamemode(
        mode: Annotated[GameMode, Field(description="Game mode for new players.")],
    ) -> ToolResult:
        """Set the game mode that players get when they first join."""
        bridge.call("defaultgamemode", mode)
        return ok({"default_gamemode": mode})

    @reg.tool(GROUP, "Get world border", read_only=True)
    def get_world_border() -> ToolResult:
        """The main world's border: size (diameter), centre, damage and warning settings."""
        return ok(bridge.call("worldborder", "get"))

    @reg.tool(GROUP, "Change world border")
    def set_world_border(
        size: Annotated[float | None, Field(ge=1, le=60_000_000, description="New diameter in blocks.")] = None,
        grow_by: Annotated[
            float | None,
            Field(
                ge=-60_000_000,
                le=60_000_000,
                description="Change the diameter by this much (negative shrinks).",
            ),
        ] = None,
        transition_seconds: Annotated[
            int | None,
            Field(ge=0, le=1_000_000, description="Animate the size change over this many seconds."),
        ] = None,
        center_x: Annotated[
            float | None, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="New centre X (with center_z).")
        ] = None,
        center_z: Annotated[
            float | None, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="New centre Z (with center_x).")
        ] = None,
        damage_per_block: Annotated[
            float | None, Field(ge=0, le=1_000, description="Damage per second per block outside the border.")
        ] = None,
        warning_distance: Annotated[
            int | None,
            Field(ge=0, le=60_000_000, description="Show the warning this many blocks from the border."),
        ] = None,
        warning_time_seconds: Annotated[
            int | None,
            Field(ge=0, le=1_000_000, description="Show the warning this many seconds before it shrinks past."),
        ] = None,
    ) -> ToolResult:
        """Change any combination of the main world's border settings in one call; omitted settings are
        left alone. Returns the resulting border."""
        if size is not None and grow_by is not None:
            raise InvalidInputError("Give either size or grow_by, not both.")
        centred = all_or_none("center_x and center_z", center_x, center_z)
        resized = size is not None or grow_by is not None
        if transition_seconds is not None and not resized:
            raise InvalidInputError("transition_seconds needs size or grow_by.")
        warned = warning_distance is not None or warning_time_seconds is not None
        if not (centred or resized or warned or damage_per_block is not None):
            raise InvalidInputError("Give at least one border setting to change.")
        changed = []
        if centred:
            bridge.call("worldborder", "center", x=center_x, z=center_z)
            changed.append("center")
        if resized:
            action, amount = ("set", size) if size is not None else ("add", grow_by)
            bridge.call("worldborder", action, value=amount, time=transition_seconds)
            changed.append("size")
        if damage_per_block is not None:
            bridge.call("worldborder", "damage", value=damage_per_block)
            changed.append("damage")
        if warned:
            bridge.call("worldborder", "warning", value=warning_distance, time=warning_time_seconds)
            changed.append("warning")
        return ok({"changed": changed, "border": bridge.call("worldborder", "get")})

    @reg.tool(GROUP, "Check chunk force-loading", read_only=True)
    def get_chunk_force_loaded(x: X, z: Z) -> ToolResult:
        """Whether the chunk containing block (x, z) of the main world is force-loaded."""
        loaded = bridge.call("forceload", "query", x, z)
        return ok({"x": x, "z": z, "chunk_x": x >> 4, "chunk_z": z >> 4, "force_loaded": bool(loaded)})

    @reg.tool(GROUP, "Force-load chunk", idempotent=True)
    def set_chunk_force_loaded(
        x: X,
        z: Z,
        force_loaded: Annotated[
            bool, Field(description="True keeps the chunk loaded without players; false releases it.")
        ],
    ) -> ToolResult:
        """Keep (or stop keeping) the chunk containing block (x, z) of the main world loaded, so redstone and
        farms there run without players nearby."""
        bridge.call("forceload", "add" if force_loaded else "remove", x, z)
        return ok({"x": x, "z": z, "chunk_x": x >> 4, "chunk_z": z >> 4, "force_loaded": force_loaded})

    @reg.tool(GROUP, "Fill biome", destructive=True, idempotent=True)
    def fill_biome(
        x1: X1,
        y1: Y1,
        z1: Z1,
        x2: X2,
        y2: Y2,
        z2: Z2,
        biome: BiomeId,
        replace_biome: Annotated[
            str | None,
            Field(
                min_length=1,
                max_length=256,
                pattern=r"^#?[A-Za-z0-9_.:/\-]+$",
                description="Only replace this biome or #tag (e.g. 'plains' or '#minecraft:is_forest').",
            ),
        ] = None,
    ) -> ToolResult:
        """Change the biome of a box in the main world (affects grass/water colour, weather and mob spawns;
        players may need to rejoin to see colours change). Refuses boxes over {max_blocks} blocks; the plugin
        only reports whether the vanilla /fillbiome command was dispatched."""
        enforce_block_limit(region_volume(x1, y1, z1, x2, y2, z2), limit, "This biome fill")
        low, high = box(x1, y1, z1, x2, y2, z2)
        dispatched = bridge.call("fillbiome", x1, y1, z1, x2, y2, z2, biome, replace_biome)
        return ok(
            {
                "from": low,
                "to": high,
                "biome": biome,
                "replace_biome": replace_biome,
                "dispatched": bool(dispatched),
            }
        )

    @reg.tool(GROUP, "Locate structure", read_only=True)
    def locate_structure(
        structure: StructureId,
        x: Annotated[
            int | None,
            Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Search from this X (with z); default: world spawn."),
        ] = None,
        z: Annotated[
            int | None,
            Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Search from this Z (with x); default: world spawn."),
        ] = None,
    ) -> ToolResult:
        """Find the nearest structure of a type in the main world, searching up to 100 chunks out.
        Can take a few seconds and may generate chunks."""
        all_or_none("x and z", x, z)
        return ok({"structure": structure, **bridge.call("locate", structure, x, z)})

    @reg.tool(GROUP, "Place feature", destructive=True)
    def place_feature(feature: FeatureId, x: OptX = None, y: OptY = None, z: OptZ = None) -> ToolResult:
        """Generate a configured feature (tree, ore vein, dungeon, ...) like world generation does. Without
        coordinates it is placed at world spawn. Only whether the command was dispatched is reported."""
        given = all_or_none("x, y and z", x, y, z)
        dispatched = bridge.call("placeFeature", feature, x, y, z)
        return ok(
            {
                "feature": feature,
                "position": {"x": x, "y": y, "z": z} if given else None,
                "dispatched": bool(dispatched),
            }
        )

    @reg.tool(GROUP, "Place structure", destructive=True)
    def place_structure(structure: StructureId, x: OptX = None, y: OptY = None, z: OptZ = None) -> ToolResult:
        """Generate a whole structure (village, temple, ...) like world generation does; it can be large and
        overwrites terrain. Without coordinates it is placed at world spawn. Only dispatch is reported."""
        given = all_or_none("x, y and z", x, y, z)
        dispatched = bridge.call("placeStructure", structure, x, y, z)
        return ok(
            {
                "structure": structure,
                "position": {"x": x, "y": y, "z": z} if given else None,
                "dispatched": bool(dispatched),
            }
        )

    @reg.tool(GROUP, "Place jigsaw structure", destructive=True)
    def place_jigsaw(
        pool: PoolId,
        target: JigsawTarget,
        max_depth: Annotated[int, Field(ge=1, le=20, description="How many jigsaw levels to expand (1-20).")],
        x: OptX = None,
        y: OptY = None,
        z: OptZ = None,
    ) -> ToolResult:
        """Generate a jigsaw structure from a template pool. Without coordinates it is placed at world spawn.
        Only dispatch is reported."""
        given = all_or_none("x, y and z", x, y, z)
        dispatched = bridge.call("placeJigsaw", pool, target, max_depth, x, y, z)
        return ok(
            {
                "pool": pool,
                "position": {"x": x, "y": y, "z": z} if given else None,
                "dispatched": bool(dispatched),
            }
        )

    @reg.tool(GROUP, "Place structure template", destructive=True, idempotent=True)
    def place_template(
        template: TemplateId,
        x: X,
        y: Y,
        z: Z,
        rotation: Annotated[
            Literal["none", "clockwise_90", "180", "counterclockwise_90"], Field(description="Rotation.")
        ] = "none",
        mirror: Annotated[Literal["none", "front_back", "left_right"], Field(description="Mirroring.")] = "none",
        integrity: Annotated[
            float, Field(ge=0, le=1, description="Fraction of blocks to place (below 1 gives a ruined look).")
        ] = 1.0,
        seed: Annotated[
            int, Field(ge=0, le=2**31 - 1, description="Seed that picks which blocks integrity drops.")
        ] = 0,
    ) -> ToolResult:
        """Place a saved structure template (structure block / NBT file) with its lowest corner at (x, y, z).
        Only dispatch is reported; verify with get_blocks."""
        dispatched = bridge.call("placeTemplate", template, x, y, z, rotation, mirror, integrity, seed)
        return ok({"template": template, "position": {"x": x, "y": y, "z": z}, "dispatched": bool(dispatched)})

    @reg.tool(GROUP, "Drop loot")
    def spawn_loot(loot_table: LootTableId, x: PosX, y: PosY, z: PosZ) -> ToolResult:
        """Roll a loot table once and drop the resulting items at a position in the main world."""
        return ok({"loot_table": loot_table, "items_dropped": bridge.call("loot", loot_table, x, y, z)})
