"""Player tools: position, movement, game mode, inventory, effects, experience, advancements."""

from typing import Annotated, Literal

from pydantic import Field

from ..errors import InvalidInputError
from ..params import (
    GameMode,
    ItemId,
    OptPitch,
    OptX,
    OptY,
    OptYaw,
    OptZ,
    PosX,
    PosY,
    PosZ,
    Username,
    all_or_none,
    resource_id,
)
from ..registry import ToolRegistry, ToolResult, ok

GROUP = "players"
INVENTORY_SLOTS = 41  # 0-35 main inventory, 36-39 armour, 40 off-hand

Slot = Annotated[
    int,
    Field(
        ge=0,
        le=INVENTORY_SLOTS - 1,
        description=(
            "Inventory slot: 0-8 hotbar, 9-35 main, 36 boots, 37 leggings, 38 chestplate, 39 helmet, 40 off-hand."
        ),
    ),
]
EffectId = resource_id("Status effect id such as 'speed', 'night_vision' or 'minecraft:regeneration'.")
EnchantmentId = resource_id("Enchantment id such as 'sharpness', 'efficiency' or 'minecraft:unbreaking'.")
AdvancementId = resource_id("Advancement id such as 'story/mine_stone' or 'minecraft:adventure/kill_a_mob'.")
SlotItem = resource_id("Item id; use 'air' to empty the slot.")
ItemFilter = resource_id("Only remove this item id; default: every item.", optional=True)
EffectFilter = resource_id("Only remove this effect; default: remove all effects.", optional=True)


def register(reg: ToolRegistry) -> None:
    bridge = reg.bridge

    @reg.tool(GROUP, "Get player position", read_only=True)
    def get_player_position(username: Username) -> ToolResult:
        """Block position of an online player's feet (rounded down); the block they stand on is at y - 1."""
        x, y, z = bridge.call("getPos", username)
        return ok({"username": username, "x": x, "y": y, "z": z})

    @reg.tool(GROUP, "Teleport player", idempotent=True)
    def teleport_player(
        username: Username, x: PosX, y: PosY, z: PosZ, yaw: OptYaw = None, pitch: OptPitch = None
    ) -> ToolResult:
        """Teleport an online player within their current world, optionally setting where they face."""
        rotated = all_or_none("yaw and pitch", yaw, pitch)
        bridge.call("teleport", username, x, y, z, yaw=yaw, pitch=pitch)
        result = {"username": username, "x": x, "y": y, "z": z}
        if rotated:
            result |= {"yaw": yaw, "pitch": pitch}
        return ok(result)

    @reg.tool(GROUP, "Set game mode", idempotent=True)
    def set_gamemode(username: Username, mode: Annotated[GameMode, Field(description="New game mode.")]) -> ToolResult:
        """Change an online player's game mode (survival, creative, adventure or spectator)."""
        bridge.call("gamemode", username, mode)
        return ok({"username": username, "gamemode": mode})

    @reg.tool(GROUP, "Give item")
    def give_item(
        username: Username,
        item: ItemId,
        amount: Annotated[int, Field(ge=1, le=64, description="Number of items (1-64).")] = 1,
    ) -> ToolResult:
        """Add items to an online player's inventory. Items that do not fit are lost."""
        bridge.call("give", username, item, amount)
        return ok({"username": username, "item": item, "amount": amount})

    @reg.tool(GROUP, "Get inventory", read_only=True)
    def get_inventory(
        username: Username,
        slots: Annotated[
            list[Slot] | None,
            Field(min_length=1, max_length=INVENTORY_SLOTS, description="Slots to read; default: all 41 slots."),
        ] = None,
    ) -> ToolResult:
        """List the non-empty inventory slots of an online player, with item, amount and enchantments.
        Slots: 0-8 hotbar, 9-35 main, 36 boots, 37 leggings, 38 chestplate, 39 helmet, 40 off-hand."""
        wanted = sorted(set(slots)) if slots else list(range(INVENTORY_SLOTS))
        items = []
        for slot in wanted:
            stack = bridge.call("getItem", username, slot)
            if stack.get("item"):
                items.append({"slot": slot, **stack})
        return ok({"username": username, "items": items, "slots_checked": len(wanted)})

    @reg.tool(GROUP, "Set inventory slot", destructive=True, idempotent=True)
    def set_inventory_slot(
        username: Username,
        slot: Slot,
        item: SlotItem,
        amount: Annotated[int, Field(ge=1, le=99, description="Stack size.")] = 1,
    ) -> ToolResult:
        """Put an item stack into one inventory slot, replacing whatever was there."""
        bridge.call("setItem", username, slot, item, amount)
        return ok({"username": username, "slot": slot, "item": item, "amount": amount})

    @reg.tool(GROUP, "Clear inventory", destructive=True)
    def clear_inventory(
        username: Username,
        item: ItemFilter = None,
        max_count: Annotated[
            int | None, Field(ge=1, description="Remove at most this many items; default: all.")
        ] = None,
    ) -> ToolResult:
        """Remove items from an online player's inventory (all items, or only one item type)."""
        removed = bridge.call("clear", username, item, -1 if max_count is None else max_count)
        return ok({"username": username, "items_removed": removed})

    @reg.tool(GROUP, "Enchant held item", idempotent=True)
    def enchant_held_item(
        username: Username,
        enchantment: EnchantmentId,
        level: Annotated[
            int,
            Field(ge=1, le=255, description="Enchantment level; levels above vanilla maxima are allowed."),
        ] = 1,
    ) -> ToolResult:
        """Add an enchantment to the item in an online player's main hand (fails if the hand is empty)."""
        bridge.call("enchant", username, enchantment, level)
        return ok({"username": username, "enchantment": enchantment, "level": level})

    @reg.tool(GROUP, "Apply status effect", idempotent=True)
    def apply_effect(
        username: Username,
        effect: EffectId,
        duration_seconds: Annotated[int, Field(ge=1, le=1_000_000, description="Duration in seconds.")] = 30,
        amplifier: Annotated[int, Field(ge=0, le=255, description="0 = level I, 1 = level II, ...")] = 0,
        hide_particles: Annotated[bool, Field(description="Hide the effect's particles.")] = False,
    ) -> ToolResult:
        """Give an online player a status effect such as speed, night_vision or regeneration."""
        applied = bridge.call("effect", username, effect, duration_seconds, amplifier, hide_particles)
        return ok({"username": username, "effect": effect, "applied": bool(applied)})

    @reg.tool(GROUP, "Clear status effects", idempotent=True)
    def clear_effects(username: Username, effect: EffectFilter = None) -> ToolResult:
        """Remove one or all status effects from an online player."""
        bridge.call("clearEffect", username, effect)
        return ok({"username": username, "cleared": effect or "all"})

    @reg.tool(GROUP, "Get experience", read_only=True)
    def get_experience(username: Username) -> ToolResult:
        """An online player's experience: level, total points and progress (0-1) toward the next level."""
        return ok({"username": username, **bridge.call("experience", username, "query", 0, "points")})

    @reg.tool(GROUP, "Change experience")
    def update_experience(
        username: Username,
        amount: Annotated[int, Field(ge=-1_000_000, le=1_000_000, description="Amount to add or set.")],
        mode: Annotated[Literal["add", "set"], Field(description="Add to or replace the current value.")] = "add",
        unit: Annotated[
            Literal["points", "levels"], Field(description="Whether amount is in points or levels.")
        ] = "points",
    ) -> ToolResult:
        """Add or set an online player's experience. Note: mode='set' with unit='points' sets the progress bar
        within the current level (amount / points needed for the next level), not the total points."""
        if mode == "set" and amount < 0:
            raise InvalidInputError("amount must not be negative when mode is 'set'.")
        return ok({"username": username, **bridge.call("experience", username, mode, amount, unit)})

    @reg.tool(GROUP, "Set spawn point", idempotent=True)
    def set_spawnpoint(username: Username, x: OptX = None, y: OptY = None, z: OptZ = None) -> ToolResult:
        """Set where an online player respawns: the given position, or where they stand now."""
        given = all_or_none("x, y and z", x, y, z)
        bridge.call("spawnpoint", username, x, y, z)
        return ok({"username": username, "spawnpoint": {"x": x, "y": y, "z": z} if given else "current position"})

    @reg.tool(GROUP, "Check advancement", read_only=True)
    def get_advancement(username: Username, advancement: AdvancementId) -> ToolResult:
        """Whether an online player has completed an advancement."""
        done = bridge.call("advancement", username, "query", advancement)
        return ok({"username": username, "advancement": advancement, "done": bool(done)})

    @reg.tool(GROUP, "Grant or revoke advancement", destructive=True, idempotent=True)
    def set_advancement(
        username: Username,
        advancement: AdvancementId,
        granted: Annotated[bool, Field(description="True grants every criterion; false revokes all progress.")],
    ) -> ToolResult:
        """Grant or revoke an advancement for an online player."""
        bridge.call("advancement", username, "grant" if granted else "revoke", advancement)
        return ok({"username": username, "advancement": advancement, "granted": granted})

    @reg.tool(GROUP, "Spread players")
    def spread_players(
        usernames: Annotated[list[Username], Field(min_length=1, max_length=100, description="Players to spread out.")],
        center_x: Annotated[float, Field(ge=-30_000_000, le=30_000_000, description="X of the centre point.")],
        center_z: Annotated[float, Field(ge=-30_000_000, le=30_000_000, description="Z of the centre point.")],
        spread_distance: Annotated[float, Field(ge=0, le=10_000, description="Minimum distance between players.")],
        max_range: Annotated[float, Field(gt=0, le=30_000_000, description="Maximum distance from the centre.")],
    ) -> ToolResult:
        """Teleport players to random surface positions around a centre point (vanilla /spreadplayers)."""
        if max_range < spread_distance + 1:
            raise InvalidInputError("max_range must be at least spread_distance + 1.")
        dispatched = bridge.call("spreadplayers", center_x, center_z, spread_distance, max_range, usernames)
        return ok({"usernames": usernames, "dispatched": bool(dispatched)})
