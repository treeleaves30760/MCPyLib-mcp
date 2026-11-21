"""Exception types.

Every subclass of :class:`McpylibMcpError` carries a message that is safe to show to the
model and the user: it never contains the MCPyLib token.
"""


class McpylibMcpError(Exception):
    """Base class for errors raised by mcpylib-mcp itself."""


class ConfigError(McpylibMcpError):
    """Invalid or missing configuration, detected at startup."""


class MinecraftError(McpylibMcpError):
    """The Minecraft server could not be reached, refused the token, or rejected a command."""


class SafetyLimitError(McpylibMcpError):
    """A request was refused locally because it exceeds a configured safety limit."""


class InvalidInputError(McpylibMcpError):
    """Tool arguments are well-typed but semantically invalid (e.g. a ragged block array)."""
