"""Safety guards: per-call block limits and tool allow/deny filtering."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase

from .errors import ConfigError, SafetyLimitError

GROUP_PREFIX = "group:"


def region_volume(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> int:
    """Number of blocks in the inclusive box spanned by two corners (in any order)."""
    return (abs(x2 - x1) + 1) * (abs(y2 - y1) + 1) * (abs(z2 - z1) + 1)


def enforce_block_limit(count: int, limit: int, what: str) -> None:
    """Refuse operations that would read or change more than ``limit`` blocks."""
    if count > limit:
        raise SafetyLimitError(
            f"{what} covers {count:,} blocks, more than the per-call limit of {limit:,} "
            "(MCPYLIB_MAX_BLOCKS). Split the work into smaller regions; only raise "
            "MCPYLIB_MAX_BLOCKS if a change this large is really intended."
        )


@dataclass(frozen=True)
class ToolInfo:
    """What the filter needs to know about a tool."""

    name: str
    group: str
    read_only: bool


def _matches(entry: str, tool: ToolInfo) -> bool:
    if entry.startswith(GROUP_PREFIX):
        return tool.group == entry[len(GROUP_PREFIX) :]
    return fnmatchcase(tool.name, entry)


def _resolve(entries: Sequence[str], catalog: Sequence[ToolInfo], source: str) -> set[str]:
    names: set[str] = set()
    for entry in entries:
        matched = {tool.name for tool in catalog if _matches(entry, tool)}
        if not matched:
            groups = ", ".join(sorted({GROUP_PREFIX + tool.group for tool in catalog}))
            raise ConfigError(
                f"{source}: {entry!r} does not match any tool. Use tool names (see "
                f"'mcpylib-mcp --list-tools'), glob patterns such as 'get_*', or groups: {groups}."
            )
        names |= matched
    return names


def select_tools(
    catalog: Sequence[ToolInfo],
    *,
    read_only: bool,
    allowed: Sequence[str],
    denied: Sequence[str],
) -> list[str]:
    """Names of the tools to register, in catalog order.

    Read-only mode keeps only non-mutating tools, a non-empty allowlist keeps only matching
    tools, and the denylist always wins. Entries that match nothing are configuration errors,
    so that a typo can never leave a tool enabled that the operator meant to deny.
    """
    allowed_names = _resolve(allowed, catalog, "MCPYLIB_ALLOWED_TOOLS (--allow-tools)") if allowed else None
    denied_names = _resolve(denied, catalog, "MCPYLIB_DENIED_TOOLS (--deny-tools)")
    return [
        tool.name
        for tool in catalog
        if (tool.read_only or not read_only)
        and (allowed_names is None or tool.name in allowed_names)
        and tool.name not in denied_names
    ]
