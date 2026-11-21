"""Server-level tools: who is online, and the raw command escape hatch."""

from typing import Annotated

from pydantic import Field

from ..registry import ToolRegistry, ToolResult, ok

GROUP = "server"


def register(reg: ToolRegistry) -> None:
    bridge = reg.bridge

    @reg.tool(GROUP, "List online players", read_only=True)
    def get_players() -> ToolResult:
        """List the players currently online (name, UUID, game mode) and the server's player limit."""
        return ok(bridge.call("list"))

    @reg.tool(GROUP, "Run a console command", destructive=True)
    def run_command(
        command: Annotated[
            str,
            Field(
                min_length=1,
                max_length=32_000,
                pattern=r"^[^\r\n]+$",
                description="One command line, with or without the leading '/', e.g. 'weather clear' or '/say hi'.",
            ),
        ],
    ) -> ToolResult:
        """Run any Minecraft command as the server console.

        Unrestricted escape hatch: it can do anything an operator can, including stopping the server,
        and the per-call block limit does not apply. Prefer the dedicated tools. The plugin only reports
        whether the command was dispatched; the command's output is not returned.
        """
        return ok({"command": command, "dispatched": bool(bridge.call("exec", command))})
