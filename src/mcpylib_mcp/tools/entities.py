"""Entity tools: summon, find, move, equip, tag and remove mobs and other entities."""

from typing import Annotated, Literal

from pydantic import Field

from ..errors import InvalidInputError, MinecraftError
from ..params import (
    EntityUUID,
    OptPitch,
    OptYaw,
    Pitch,
    PosX,
    PosY,
    PosZ,
    Trade,
    Yaw,
    all_or_none,
    entity_uuid,
    resource_id,
)
from ..registry import ToolRegistry, ToolResult, ok

GROUP = "entities"

EntityType = resource_id("Entity type such as 'zombie', 'villager' or 'minecraft:armor_stand'.")
AttributeId = resource_id("Attribute such as 'max_health', 'movement_speed', 'attack_damage' or 'scale'.")
EquipmentItem = resource_id("Item id for this slot ('air' empties it).", optional=True)
EquipmentSlot = Literal["helmet", "chestplate", "leggings", "boots", "main_hand", "off_hand"]
Chance = Annotated[float, Field(ge=0, le=1)]
TargetUUID = entity_uuid("UUID of the living entity to attack; omit to clear the target.", optional=True)
SourceUUID = entity_uuid("Entity to blame for the damage (affects aggro and kill credit).", optional=True)
PassengerUUID = entity_uuid("Entity that rides.")
VehicleUUID = entity_uuid(
    "Entity to ride (horse, boat, minecart, pig, another mob...); omit to dismount.", optional=True
)
Tag = Annotated[str, Field(min_length=1, max_length=256, pattern=r"^\S+$", description="Scoreboard tag.")]
Velocity = Annotated[float, Field(ge=-10, le=10, description="Blocks per tick (20 ticks per second), -10 to 10.")]
Profession = Literal[
    "none",
    "armorer",
    "butcher",
    "cartographer",
    "cleric",
    "farmer",
    "fisherman",
    "fletcher",
    "leatherworker",
    "librarian",
    "mason",
    "nitwit",
    "shepherd",
    "toolsmith",
    "weaponsmith",
]


def register(reg: ToolRegistry) -> None:
    bridge = reg.bridge

    @reg.tool(GROUP, "Summon entity")
    def summon_entity(entity_type: EntityType, x: PosX, y: PosY, z: PosZ) -> ToolResult:
        """Spawn an entity in the main world and return its UUID (used by every other entity tool)."""
        uuid = bridge.call("summon", entity_type, x, y, z)
        return ok({"uuid": uuid, "entity_type": entity_type, "x": x, "y": y, "z": z})

    @reg.tool(GROUP, "Kill entities", destructive=True, idempotent=True)
    def kill_entities(
        target: Annotated[
            str,
            Field(
                min_length=1,
                max_length=256,
                pattern=r"^(all|player:\S+|[A-Za-z0-9_.:\-]+)$",
                description="An entity type such as 'zombie', 'player:<name>' to kill one player, or 'all'.",
            ),
        ],
    ) -> ToolResult:
        """Remove entities from the main world (at most 1,000 per call). Mobs are removed without drops;
        a killed player dies normally and drops their items. 'all' removes EVERY non-player entity,
        including pets, villagers, item frames, armor stands, paintings, boats and minecarts: prefer a
        specific type, or remove_entity for one entity."""
        return ok({"target": target, "count": bridge.call("kill", target)})

    @reg.tool(GROUP, "Remove entity", destructive=True, idempotent=True)
    def remove_entity(uuid: EntityUUID) -> ToolResult:
        """Delete one entity (not a player) without drops or death animation."""
        bridge.call("removeEntity", uuid)
        return ok({"uuid": uuid, "removed": True})

    @reg.tool(GROUP, "Get entity", read_only=True)
    def get_entity(uuid: EntityUUID) -> ToolResult:
        """Details of one entity: type, custom name, world, position, rotation, velocity, health and AI state."""
        status = bridge.call("getEntityStatus", uuid)
        try:
            position = bridge.call("getEntityPos", uuid)
        except MinecraftError:  # the entity can vanish between the two calls
            position = None
        if position:
            status["rotation"] = {"yaw": position.get("yaw"), "pitch": position.get("pitch")}
        return ok(status)

    @reg.tool(GROUP, "Teleport entity", idempotent=True)
    def teleport_entity(
        uuid: EntityUUID, x: PosX, y: PosY, z: PosZ, yaw: OptYaw = None, pitch: OptPitch = None
    ) -> ToolResult:
        """Move an entity to an exact position, optionally setting where it faces."""
        rotated = all_or_none("yaw and pitch", yaw, pitch)
        bridge.call("teleportEntity", uuid, x, y, z, yaw=yaw, pitch=pitch)
        result = {"uuid": uuid, "x": x, "y": y, "z": z}
        if rotated:
            result |= {"yaw": yaw, "pitch": pitch}
        return ok(result)

    @reg.tool(GROUP, "Set entity velocity", idempotent=True)
    def set_entity_velocity(uuid: EntityUUID, vx: Velocity, vy: Velocity, vz: Velocity) -> ToolResult:
        """Push an entity: set its velocity vector (e.g. vy=1 for a jump of about 7 blocks)."""
        bridge.call("setEntityVelocity", uuid, vx, vy, vz)
        return ok({"uuid": uuid, "velocity": {"x": vx, "y": vy, "z": vz}})

    @reg.tool(GROUP, "Set entity rotation", idempotent=True)
    def set_entity_rotation(uuid: EntityUUID, yaw: Yaw, pitch: Pitch) -> ToolResult:
        """Turn an entity to face a direction without moving it."""
        bridge.call("setEntityRotation", uuid, yaw, pitch)
        return ok({"uuid": uuid, "yaw": yaw, "pitch": pitch})

    @reg.tool(GROUP, "Enable or disable entity AI", idempotent=True)
    def set_entity_ai(
        uuid: EntityUUID,
        enabled: Annotated[bool, Field(description="False freezes the mob like a statue; true restores its AI.")],
    ) -> ToolResult:
        """Turn a mob's AI on or off (living entities only)."""
        bridge.call("setEntityAI", uuid, enabled)
        return ok({"uuid": uuid, "ai_enabled": enabled})

    @reg.tool(GROUP, "Set mob target", idempotent=True)
    def set_entity_target(uuid: EntityUUID, target_uuid: TargetUUID = None) -> ToolResult:
        """Make a mob attack a specific living entity, or clear its target."""
        bridge.call("setEntityTarget", uuid, target_uuid)
        return ok({"uuid": uuid, "target_uuid": target_uuid})

    @reg.tool(GROUP, "Get entity equipment", read_only=True)
    def get_entity_equipment(uuid: EntityUUID) -> ToolResult:
        """Items in a living entity's armour and hand slots (null for empty slots)."""
        return ok({"uuid": uuid, "equipment": bridge.call("getEntityEquipment", uuid)})

    @reg.tool(GROUP, "Set entity equipment", destructive=True, idempotent=True)
    def set_entity_equipment(
        uuid: EntityUUID,
        helmet: EquipmentItem = None,
        chestplate: EquipmentItem = None,
        leggings: EquipmentItem = None,
        boots: EquipmentItem = None,
        main_hand: EquipmentItem = None,
        off_hand: EquipmentItem = None,
        drop_chances: Annotated[
            dict[EquipmentSlot, Chance] | None,
            Field(description="Chance (0-1) that each slot's item drops when the mob dies."),
        ] = None,
    ) -> ToolResult:
        """Equip a living entity (mob or armor stand); slots you omit are left unchanged, and the replaced
        items are lost."""
        given = {
            "helmet": helmet,
            "chestplate": chestplate,
            "leggings": leggings,
            "boots": boots,
            "main_hand": main_hand,
            "off_hand": off_hand,
        }
        equipment = {slot: item for slot, item in given.items() if item is not None}
        if not equipment and not drop_chances:
            raise InvalidInputError("Give at least one equipment slot or drop chance.")
        bridge.call("setEntityEquipment", uuid, equipment, drop_chances)
        return ok({"uuid": uuid, "equipment": equipment, "drop_chances": drop_chances})

    @reg.tool(GROUP, "Damage entity", destructive=True)
    def damage_entity(
        uuid: EntityUUID,
        amount: Annotated[float, Field(gt=0, le=1_000_000, description="Damage in health points (2 = one heart).")],
        source_uuid: SourceUUID = None,
    ) -> ToolResult:
        """Hurt a living entity. Enough damage kills it."""
        bridge.call("damage", uuid, amount, source_uuid)
        return ok({"uuid": uuid, "amount": amount})

    @reg.tool(GROUP, "Mount or dismount", idempotent=True)
    def ride_entity(passenger_uuid: PassengerUUID, vehicle_uuid: VehicleUUID = None) -> ToolResult:
        """Make one entity ride another, or dismount it."""
        changed = bridge.call("ride", passenger_uuid, vehicle_uuid)
        return ok({"passenger_uuid": passenger_uuid, "vehicle_uuid": vehicle_uuid, "changed": bool(changed)})

    @reg.tool(GROUP, "Get entity attribute", read_only=True)
    def get_entity_attribute(uuid: EntityUUID, attribute: AttributeId) -> ToolResult:
        """Base and effective value of a living entity's attribute (e.g. max_health, movement_speed)."""
        return ok({"uuid": uuid, "attribute": attribute, **bridge.call("attribute", uuid, attribute, "get")})

    @reg.tool(GROUP, "Set entity attribute", idempotent=True)
    def set_entity_attribute(
        uuid: EntityUUID,
        attribute: AttributeId,
        base_value: Annotated[float, Field(ge=-1_000_000, le=1_000_000, description="New base value.")],
    ) -> ToolResult:
        """Set the base value of a living entity's attribute, e.g. max_health 40 or scale 2."""
        return ok(
            {
                "uuid": uuid,
                "attribute": attribute,
                **bridge.call("attribute", uuid, attribute, "set", base_value),
            }
        )

    @reg.tool(GROUP, "Get entity tags", read_only=True)
    def get_entity_tags(uuid: EntityUUID) -> ToolResult:
        """An entity's scoreboard tags: labels usable in selectors such as @e[tag=boss]."""
        return ok({"uuid": uuid, "tags": bridge.call("getTags", uuid)})

    @reg.tool(GROUP, "Add or remove entity tags", idempotent=True)
    def update_entity_tags(
        uuid: EntityUUID,
        add: Annotated[list[Tag] | None, Field(max_length=100, description="Tags to add.")] = None,
        remove: Annotated[list[Tag] | None, Field(max_length=100, description="Tags to remove (after adding).")] = None,
    ) -> ToolResult:
        """Add and/or remove scoreboard tags on an entity and return its resulting tags."""
        if not add and not remove:
            raise InvalidInputError("Give tags to add and/or remove.")
        for tag in add or ():
            bridge.call("addTag", uuid, tag)
        for tag in remove or ():
            bridge.call("removeTag", uuid, tag)
        return ok({"uuid": uuid, "added": add or [], "removed": remove or [], "tags": bridge.call("getTags", uuid)})

    @reg.tool(GROUP, "Get villager", read_only=True)
    def get_villager(uuid: EntityUUID) -> ToolResult:
        """A villager's profession, level and trades (with uses and limits)."""
        return ok({"uuid": uuid, **bridge.call("getVillagerData", uuid)})

    @reg.tool(GROUP, "Set villager profession", destructive=True, idempotent=True)
    def set_villager_profession(
        uuid: EntityUUID, profession: Annotated[Profession, Field(description="New profession.")]
    ) -> ToolResult:
        """Change a villager's profession. This resets the villager's current trades."""
        bridge.call("setVillagerProfession", uuid, profession)
        return ok({"uuid": uuid, "profession": profession})

    @reg.tool(GROUP, "Set villager trades", destructive=True, idempotent=True)
    def set_villager_trades(
        uuid: EntityUUID,
        trades: Annotated[list[Trade], Field(max_length=100, description="The complete new trade list, in order.")],
    ) -> ToolResult:
        """Replace all of a villager's trades with custom ones."""
        bridge.call("setVillagerTrades", uuid, [trade.to_mcpylib() for trade in trades])
        return ok({"uuid": uuid, "trades": len(trades)})
