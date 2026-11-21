"""Chat, titles, sounds and particles."""

import json
from typing import Annotated, Any, Literal

from pydantic import Field

from ..errors import InvalidInputError
from ..params import XZ_LIMIT, OptPosX, OptPosY, OptPosZ, PosX, PosY, PosZ, Username, all_or_none, resource_id
from ..registry import ToolRegistry, ToolResult, ok

GROUP = "chat"

Message = Annotated[str, Field(min_length=1, max_length=4096, description="Message text.")]
SoundId = resource_id("Sound event such as 'entity.experience_orb.pickup' or 'block.note_block.harp'.")
SoundFilter = resource_id("Sound to stop; omit (with source) to stop every sound.", optional=True)
SoundSource = Literal[
    "master", "music", "record", "weather", "block", "hostile", "neutral", "player", "ambient", "voice"
]
ParticleId = resource_id(
    "Particle such as 'flame', 'heart', 'happy_villager', 'end_rod', 'cloud' or 'soul_fire_flame'. "
    "Particles that need extra data (dust, block, item) are not supported."
)
Ticks = Annotated[int, Field(ge=0, le=12_000, description="Duration in ticks (20 ticks = 1 second).")]
Spread = Annotated[float, Field(ge=0, le=XZ_LIMIT, description="Random spread along this axis, in blocks.")]


def register(reg: ToolRegistry) -> None:
    bridge = reg.bridge

    @reg.tool(GROUP, "Broadcast message")
    def broadcast_message(message: Message) -> ToolResult:
        """Send a chat message to every player; it appears as '[Server] <message>'."""
        bridge.call("say", message)
        return ok({"message": message, "sent": True})

    @reg.tool(GROUP, "Message a player")
    def send_message(username: Username, message: Message) -> ToolResult:
        """Send a private chat message to one online player."""
        bridge.call("tell", username, message)
        return ok({"username": username, "message": message, "sent": True})

    @reg.tool(GROUP, "Send formatted message")
    def send_rich_message(
        target: Annotated[
            str,
            Field(
                min_length=1,
                max_length=256,
                pattern=r"^\S+$",
                description="Player name or selector such as @a or @a[distance=..10] (no spaces).",
            ),
        ],
        text: Annotated[
            str | dict[str, Any] | list[Any],
            Field(
                description=(
                    "Raw JSON text component, e.g. {'text': 'Hello', 'color': 'gold', 'bold': true}, or a list of "
                    "components. Plain text is wrapped as {'text': ...}."
                )
            ),
        ],
    ) -> ToolResult:
        """Send a formatted (coloured, clickable, hoverable) chat message using vanilla /tellraw."""
        if isinstance(text, str):
            try:
                json.loads(text)
                component = text
            except ValueError:
                component = json.dumps({"text": text}, ensure_ascii=False)
        else:
            component = json.dumps(text, ensure_ascii=False)
        dispatched = bridge.call("tellraw", target, component)
        return ok({"target": target, "dispatched": bool(dispatched)})

    @reg.tool(GROUP, "Show title")
    def show_title(
        username: Username,
        title: Annotated[str, Field(max_length=1024, description="Large title text.")] = "",
        subtitle: Annotated[str, Field(max_length=1024, description="Smaller text below the title.")] = "",
        fade_in: Ticks = 10,
        stay: Ticks = 70,
        fade_out: Ticks = 20,
    ) -> ToolResult:
        """Show a big title and/or subtitle in the middle of an online player's screen."""
        if not title and not subtitle:
            raise InvalidInputError("Give a title or subtitle.")
        bridge.call("title", username, title, subtitle, fade_in, stay, fade_out)
        return ok({"username": username, "title": title, "subtitle": subtitle})

    @reg.tool(GROUP, "Play sound")
    def play_sound(
        username: Username,
        sound: SoundId,
        source: Annotated[SoundSource, Field(description="Volume slider category the sound uses.")] = "master",
        x: OptPosX = None,
        y: OptPosY = None,
        z: OptPosZ = None,
        volume: Annotated[
            float, Field(ge=0, le=10, description="Volume; above 1 mainly extends the hearing range.")
        ] = 1.0,
        pitch: Annotated[float, Field(ge=0.5, le=2.0, description="Playback speed/pitch, 0.5-2.")] = 1.0,
    ) -> ToolResult:
        """Play a sound to one online player, at a position or (by default) at the player."""
        all_or_none("x, y and z", x, y, z)
        bridge.call("playsound", username, sound, source, x, y, z, volume, pitch)
        return ok({"username": username, "sound": sound})

    @reg.tool(GROUP, "Stop sounds", idempotent=True)
    def stop_sound(
        username: Username,
        sound: SoundFilter = None,
        source: Annotated[SoundSource | None, Field(description="Only stop the sound in this category.")] = None,
    ) -> ToolResult:
        """Stop sounds playing for an online player: one sound, or everything."""
        if source is not None and sound is None:
            raise InvalidInputError("source only applies together with sound; omit both to stop every sound.")
        bridge.call("stopsound", username, sound, source)
        return ok({"username": username, "stopped": sound or "all"})

    @reg.tool(GROUP, "Spawn particles")
    def spawn_particles(
        particle: ParticleId,
        x: PosX,
        y: PosY,
        z: PosZ,
        count: Annotated[int, Field(ge=1, le=10_000, description="Number of particles.")] = 1,
        dx: Spread = 0,
        dy: Spread = 0,
        dz: Spread = 0,
        speed: Annotated[float, Field(ge=0, le=100, description="Particle speed.")] = 0,
    ) -> ToolResult:
        """Show particles at a position in the main world (visible to nearby players)."""
        bridge.call("particle", particle, x, y, z, count, dx, dy, dz, speed)
        return ok({"particle": particle, "x": x, "y": y, "z": z, "count": count})
