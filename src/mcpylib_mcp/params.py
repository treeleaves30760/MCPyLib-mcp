"""Reusable, documented parameter types for tool signatures.

Every alias carries a description and bounds, so the generated JSON schemas tell the model
exactly what to send and malformed values are rejected before anything reaches the server.
Identifiers never contain whitespace: several plugin commands splice them into console command
lines, and whitespace would let a value smuggle in extra command arguments.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .errors import InvalidInputError

XZ_LIMIT = 30_000_000  # Minecraft's world border maximum
Y_MIN, Y_MAX = -2048, 2047  # widest build-height range a datapack can configure
ID_PATTERN = r"^[A-Za-z0-9_.:/\-]+$"
NO_SPACE_PATTERN = r"^\S+$"
UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

# ---------------------------------------------------------------- block coordinates
X = Annotated[int, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Block X coordinate (east is +X).")]
Y = Annotated[
    int,
    Field(
        ge=Y_MIN,
        le=Y_MAX,
        description="Block Y coordinate (height; the overworld build range is -64 to 319).",
    ),
]
Z = Annotated[int, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Block Z coordinate (south is +Z).")]
X1 = Annotated[int, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="X of one corner of the box (inclusive).")]
Y1 = Annotated[int, Field(ge=Y_MIN, le=Y_MAX, description="Y of one corner of the box (inclusive).")]
Z1 = Annotated[int, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Z of one corner of the box (inclusive).")]
X2 = Annotated[int, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="X of the opposite corner (inclusive).")]
Y2 = Annotated[int, Field(ge=Y_MIN, le=Y_MAX, description="Y of the opposite corner (inclusive).")]
Z2 = Annotated[int, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Z of the opposite corner (inclusive).")]
OptX = Annotated[
    int | None,
    Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Block X; give x, y and z together or leave all out."),
]
OptY = Annotated[
    int | None, Field(ge=Y_MIN, le=Y_MAX, description="Block Y; give x, y and z together or leave all out.")
]
OptZ = Annotated[
    int | None,
    Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Block Z; give x, y and z together or leave all out."),
]

# ---------------------------------------------------------------- exact positions and rotation
PosX = Annotated[float, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Exact X; block centres are at .5 (e.g. 100.5).")]
PosY = Annotated[float, Field(ge=Y_MIN, le=Y_MAX, description="Exact Y of the feet.")]
PosZ = Annotated[float, Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Exact Z; block centres are at .5 (e.g. -20.5).")]
OptPosX = Annotated[
    float | None,
    Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Exact X; give x, y and z together or leave all out."),
]
OptPosY = Annotated[
    float | None, Field(ge=Y_MIN, le=Y_MAX, description="Exact Y; give x, y and z together or leave all out.")
]
OptPosZ = Annotated[
    float | None,
    Field(ge=-XZ_LIMIT, le=XZ_LIMIT, description="Exact Z; give x, y and z together or leave all out."),
]
YAW_HELP = "Horizontal facing in degrees: 0 = south, 90 = west, 180 = north, 270 (or -90) = east."
PITCH_HELP = "Vertical facing in degrees: -90 = straight up, 0 = level, 90 = straight down."
Yaw = Annotated[float, Field(ge=-360, le=360, description=YAW_HELP)]
Pitch = Annotated[float, Field(ge=-90, le=90, description=PITCH_HELP)]
OptYaw = Annotated[float | None, Field(ge=-360, le=360, description=YAW_HELP + " Give together with pitch.")]
OptPitch = Annotated[float | None, Field(ge=-90, le=90, description=PITCH_HELP + " Give together with yaw.")]

# ---------------------------------------------------------------- names and ids
Username = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=NO_SPACE_PATTERN,
        description="Exact, case-sensitive name of an online player.",
    ),
]


def resource_id(description: str, *, optional: bool = False) -> Any:
    """A namespaced id (``minecraft:`` prefix optional) without whitespace; ``optional`` allows null."""
    field = Field(min_length=1, max_length=256, pattern=ID_PATTERN, description=description)
    return Annotated[str | None, field] if optional else Annotated[str, field]


def entity_uuid(description: str, *, optional: bool = False) -> Any:
    """An entity UUID string; ``optional`` allows null."""
    field = Field(pattern=UUID_PATTERN, description=description)
    return Annotated[str | None, field] if optional else Annotated[str, field]


EntityUUID = entity_uuid("Entity UUID, e.g. as returned by summon_entity or get_players.")


BlockId = resource_id("Block id such as 'minecraft:stone' or 'oak_planks' (the minecraft: namespace is optional).")
ItemId = resource_id("Item id such as 'minecraft:diamond' or 'bread'.")
GameMode = Literal["survival", "creative", "adventure", "spectator"]

BLOCK_STATE_HELP = (
    "Block state properties, e.g. {'facing': 'north', 'half': 'top'}. Any vanilla property of the block works "
    "(type=top for slabs, hinge=left, part=head, lit=true, rotation=0-15, ...); a property the block doesn't "
    "have is an error. rotation also accepts a compass direction such as north_north_east."
)
NBT_HELP = (
    "Block-entity data. The plugin applies only CustomName (containers) and Text1-Text4 (sign lines); "
    "other keys are ignored."
)
BlockState = Annotated[dict[str, str | int | bool] | None, Field(description=BLOCK_STATE_HELP)]
Nbt = Annotated[dict[str, Any] | None, Field(description=NBT_HELP)]


def state_strings(state: dict[str, str | int | bool] | None) -> dict[str, str] | None:
    """Block state values as the strings Minecraft expects (``True`` -> ``"true"``)."""
    if state is None:
        return None
    return {key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in state.items()}


class BlockSpec(BaseModel):
    """A block with optional block state and block-entity data."""

    model_config = ConfigDict(extra="forbid")

    block: BlockId
    block_state: BlockState = None
    nbt: Nbt = None

    def to_mcpylib(self) -> dict[str, Any]:
        spec: dict[str, Any] = {"block": self.block}
        if self.block_state is not None:
            spec["block_state"] = state_strings(self.block_state)
        if self.nbt is not None:
            spec["nbt"] = self.nbt
        return spec


def block_value(value: str | BlockSpec | None) -> str | dict[str, Any] | None:
    """Convert a palette/array entry to what MCPyLib's ``edit()`` expects."""
    return value.to_mcpylib() if isinstance(value, BlockSpec) else value


class TradeItem(BaseModel):
    """One stack in a villager trade."""

    model_config = ConfigDict(extra="forbid")

    item: ItemId
    amount: Annotated[int, Field(ge=1, le=99, description="Stack size.")] = 1


class Trade(BaseModel):
    """A villager trade: buy1 (+ optional buy2) for sell."""

    model_config = ConfigDict(extra="forbid")

    buy1: Annotated[TradeItem, Field(description="First item the player pays.")]
    buy2: Annotated[TradeItem | None, Field(description="Optional second item the player pays.")] = None
    sell: Annotated[TradeItem, Field(description="Item the villager gives.")]
    max_uses: Annotated[int, Field(ge=1, le=100_000, description="Uses before the trade locks.")] = 10
    experience_reward: Annotated[bool, Field(description="Whether the trade gives the player XP.")] = True

    def to_mcpylib(self) -> dict[str, Any]:
        trade: dict[str, Any] = {"buy1": self.buy1.model_dump()}
        if self.buy2 is not None:
            trade["buy2"] = self.buy2.model_dump()
        trade |= {
            "sell": self.sell.model_dump(),
            "max_uses": self.max_uses,
            "experience_reward": self.experience_reward,
        }
        return trade


# ---------------------------------------------------------------- validation helpers
def all_or_none(names: str, *values: Any) -> bool:
    """True if every value is given, False if none is; error if only some are."""
    given = [value is not None for value in values]
    if any(given) and not all(given):
        raise InvalidInputError(f"Give {names} together, or leave them all out.")
    return all(given)


def point(x: float, y: float, z: float) -> dict[str, float]:
    return {"x": x, "y": y, "z": z}


def box(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> tuple[dict[str, int], dict[str, int]]:
    """Normalized (min corner, max corner) of a box given by two corners in any order."""
    low = {"x": min(x1, x2), "y": min(y1, y2), "z": min(z1, z2)}
    high = {"x": max(x1, x2), "y": max(y1, y2), "z": max(z1, z2)}
    return low, high
