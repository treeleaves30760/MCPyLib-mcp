"""Tool catalog: collects every tool once, then builds the subset allowed by the settings."""

from __future__ import annotations

import functools
import inspect
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from .errors import McpylibMcpError
from .safety import ToolInfo

if TYPE_CHECKING:
    from .bridge import MinecraftBridge
    from .config import Settings

# Every tool returns a JSON object as structured content (plus the same JSON as text).
ToolResult = Annotated[CallToolResult, dict[str, Any]]


def ok(data: dict[str, Any]) -> CallToolResult:
    """A successful tool result: compact JSON text plus identical structured content."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=data)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    group: str
    title: str
    description: str
    read_only: bool
    destructive: bool
    idempotent: bool
    fn: Callable[..., Any]

    @property
    def info(self) -> ToolInfo:
        return ToolInfo(self.name, self.group, self.read_only)

    @property
    def annotations(self) -> ToolAnnotations:
        return ToolAnnotations(
            title=self.title,
            read_only_hint=self.read_only,
            destructive_hint=self.destructive and not self.read_only,
            idempotent_hint=self.idempotent or self.read_only,
            open_world_hint=False,
        )


class ToolRegistry:
    """Collects tool definitions. Tool modules register closures over ``bridge`` and ``settings``."""

    def __init__(self, settings: Settings, bridge: MinecraftBridge) -> None:
        self.settings = settings
        self.bridge = bridge
        self._specs: dict[str, ToolSpec] = {}

    def tool(
        self,
        group: str,
        title: str,
        *,
        read_only: bool = False,
        destructive: bool = False,
        idempotent: bool = False,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register the decorated function as a tool; its docstring becomes the description.

        ``{max_blocks}`` in the docstring is replaced with the configured limit. Errors raised as
        :class:`McpylibMcpError` reach the model as tool errors with their message intact.
        """

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            name = fn.__name__
            if name in self._specs:
                raise ValueError(f"duplicate tool name: {name}")
            description = inspect.cleandoc(fn.__doc__ or "").replace("{max_blocks}", f"{self.settings.max_blocks:,}")
            self._specs[name] = ToolSpec(
                name=name,
                group=group,
                title=title,
                description=description,
                read_only=read_only,
                destructive=destructive,
                idempotent=idempotent,
                fn=_translate_errors(fn),
            )
            return fn

        return decorator

    @property
    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def build_tools(self, names: Iterable[str]) -> list[Tool]:
        """SDK ``Tool`` objects for the named tools, with compact JSON schemas."""
        tools = []
        for name in names:
            spec = self._specs[name]
            tool = Tool.from_function(
                spec.fn,
                name=spec.name,
                title=spec.title,
                description=spec.description,
                annotations=spec.annotations,
                structured_output=True,
            )
            tool.parameters = _strip_titles(tool.parameters)
            if tool.fn_metadata.output_schema is not None:
                tool.fn_metadata.output_schema = _strip_titles(tool.fn_metadata.output_schema)
                tool.__dict__.pop("output_schema", None)  # drop the cached copy, if any
            tools.append(tool)
        return tools


def _strip_titles(schema: Any) -> Any:
    """Remove pydantic's auto-generated ``title`` annotations; they repeat property names.

    Only string-valued ``title`` keys are annotations; a property *named* ``title`` maps to a schema
    object and is kept.
    """
    if isinstance(schema, dict):
        return {k: _strip_titles(v) for k, v in schema.items() if not (k == "title" and isinstance(v, str))}
    if isinstance(schema, list):
        return [_strip_titles(item) for item in schema]
    return schema


def _translate_errors(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Turn our own errors into ``ToolError`` so the SDK shows their message to the model."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except McpylibMcpError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper
