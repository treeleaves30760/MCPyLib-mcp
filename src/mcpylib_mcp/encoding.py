"""Compact, model-friendly encodings of block regions.

Conventions shared by every encoding (and by the ``build_from_layers`` tool):

* ``layers[y]`` is one horizontal slice, bottom (lowest Y) first;
* ``layers[y][z]`` is one row of that slice, north (lowest Z) first;
* ``layers[y][z][x]`` is one character, west (lowest X) first.

``"."`` always stands for ``minecraft:air`` and ``" "`` (space) for "nothing / leave unchanged".
MCPyLib's own 3D arrays are indexed ``[x][y][z]``; helpers here convert between the two.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import InvalidInputError, MinecraftError

AIR = "minecraft:air"
AIR_LIKE = frozenset({AIR, "minecraft:cave_air", "minecraft:void_air"})
AIR_CHAR = "."
SKIP_CHAR = " "
# Single-character labels for non-air blocks: no ".", " ", quotes, backslash or comma.
PALETTE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789#$%&*+-/:;<=>?@^_~!"

Grid = list[list[list[str]]]


def normalize_block_id(name: str) -> str:
    """Lower-case a block id and add the ``minecraft:`` namespace when it is missing."""
    name = name.strip().lower()
    return name if ":" in name else f"minecraft:{name}"


def _server_grid_shape(grid: Any) -> tuple[int, int, int]:
    """Validate a ``[x][y][z]`` grid of block ids returned by the plugin."""
    malformed = MinecraftError("The Minecraft server returned a malformed block grid.")
    if not isinstance(grid, list) or not grid:
        raise malformed
    try:
        sy = len(grid[0])
        sz = len(grid[0][0])
    except (TypeError, IndexError):
        raise malformed from None
    if sy == 0 or sz == 0:
        raise malformed
    for plane in grid:
        if not isinstance(plane, list) or len(plane) != sy:
            raise malformed
        for column in plane:
            if not isinstance(column, list) or len(column) != sz:
                raise malformed
            if not all(isinstance(block, str) for block in column):
                raise malformed
    return len(grid), sy, sz


def _count(grid: Grid) -> Counter[str]:
    return Counter(block for plane in grid for column in plane for block in column)


def _by_frequency(counts: Mapping[str, int]) -> list[str]:
    return sorted(counts, key=lambda block: (-counts[block], block))


def _assign_chars(counts: Mapping[str, int], too_many_hint: str) -> dict[str, str]:
    """Map block id -> label character, most frequent block first; air is always ``"."``."""
    ordered = _by_frequency(counts)
    non_air = [block for block in ordered if block != AIR]
    if len(non_air) > len(PALETTE_CHARS):
        raise InvalidInputError(
            f"The region contains {len(ordered)} distinct block types, more than the "
            f"{len(PALETTE_CHARS)} single-character labels available. {too_many_hint}"
        )
    labels = iter(PALETTE_CHARS)
    return {block: AIR_CHAR if block == AIR else next(labels) for block in ordered}


def _sorted_counts(counts: Mapping[str, int]) -> dict[str, int]:
    return {block: counts[block] for block in _by_frequency(counts)}


def encode_layers(grid: Grid) -> dict[str, Any]:
    """Encode a ``[x][y][z]`` grid as a character palette plus ``layers[y][z]`` strings."""
    sx, sy, sz = _server_grid_shape(grid)
    counts = _count(grid)
    char_of = _assign_chars(counts, "Use layout='xyz' or a smaller region.")
    layers = [["".join(char_of[grid[x][y][z]] for x in range(sx)) for z in range(sz)] for y in range(sy)]
    return {
        "palette": {char: block for block, char in char_of.items()},
        "layers": layers,
        "counts": _sorted_counts(counts),
    }


def encode_xyz(grid: Grid) -> dict[str, Any]:
    """Encode a ``[x][y][z]`` grid as a block palette plus ``[x][y][z]`` palette indices."""
    _server_grid_shape(grid)
    counts = _count(grid)
    palette = _by_frequency(counts)
    index = {block: i for i, block in enumerate(palette)}
    blocks = [[[index[block] for block in column] for column in plane] for plane in grid]
    return {"palette": palette, "blocks": blocks, "counts": _sorted_counts(counts)}


def summarize(grid: Grid) -> dict[str, Any]:
    """Only the block counts of a ``[x][y][z]`` grid."""
    _server_grid_shape(grid)
    return {"counts": _sorted_counts(_count(grid))}


def decode_layers(palette: Mapping[str, Any], layers: Sequence[Sequence[str]]) -> tuple[list[Any], int]:
    """Turn a palette plus ``layers[y][z]`` strings into MCPyLib's ``[x][y][z]`` array.

    Returns the array and the number of blocks it places. Space characters, and palette
    entries whose value is ``None``, become ``None`` (leave the existing block unchanged).
    """
    for key in palette:
        if len(key) != 1:
            raise InvalidInputError(f"Palette key {key!r} must be a single character.")
        if key == SKIP_CHAR:
            raise InvalidInputError(
                "The space character is reserved for 'leave unchanged' and cannot be a palette key."
            )
    if not layers:
        raise InvalidInputError("layers must contain at least one layer.")
    sz = len(layers[0])
    if sz == 0:
        raise InvalidInputError("layers[0] has no rows.")
    sx = len(layers[0][0])
    if sx == 0:
        raise InvalidInputError("layers[0][0] is empty; every row needs at least one character.")
    for y, layer in enumerate(layers):
        if len(layer) == 0:
            raise InvalidInputError(f"layers[{y}] has no rows.")
        if len(layer) != sz:
            raise InvalidInputError(
                f"layers[{y}] has {len(layer)} rows but layers[0] has {sz}; every layer needs the "
                "same number of rows (one per Z)."
            )
        for z, row in enumerate(layer):
            if len(row) != sx:
                raise InvalidInputError(
                    f"layers[{y}][{z}] has length {len(row)} but every row must have length {sx} "
                    "(one character per X); pad with spaces to leave blocks unchanged."
                )

    sy = len(layers)
    blocks: list[Any] = [[[None] * sz for _ in range(sy)] for _ in range(sx)]
    placed = 0
    for y, layer in enumerate(layers):
        for z, row in enumerate(layer):
            for x, char in enumerate(row):
                if char == SKIP_CHAR:
                    continue
                if char not in palette:
                    raise InvalidInputError(
                        f"Character {char!r} at layers[{y}][{z}][{x}] is not in the palette."
                    )
                value = palette[char]
                if value is None:
                    continue
                blocks[x][y][z] = value
                placed += 1
    return blocks, placed


def check_xyz_blocks(blocks: Sequence[Sequence[Sequence[Any]]]) -> tuple[tuple[int, int, int], int]:
    """Validate that an ``[x][y][z]`` array is rectangular; return its size and non-null count."""
    if not blocks:
        raise InvalidInputError("blocks must not be empty.")
    sy = len(blocks[0])
    if sy == 0:
        raise InvalidInputError("blocks[0] must not be empty.")
    sz = len(blocks[0][0])
    if sz == 0:
        raise InvalidInputError("blocks[0][0] must not be empty.")
    placed = 0
    for x, plane in enumerate(blocks):
        if len(plane) != sy:
            raise InvalidInputError(
                f"blocks[{x}] has {len(plane)} entries but blocks[0] has {sy}; the array must be "
                "rectangular and indexed [x][y][z]."
            )
        for y, column in enumerate(plane):
            if len(column) != sz:
                raise InvalidInputError(
                    f"blocks[{x}][{y}] has {len(column)} entries but blocks[0][0] has {sz}; the array "
                    "must be rectangular and indexed [x][y][z]."
                )
            placed += sum(1 for block in column if block is not None)
    return (len(blocks), sy, sz), placed


def height_map(grid: Grid, y_origin: int, ignore: set[str]) -> dict[str, Any]:
    """Highest non-air (and non-ignored) block of every column in a ``[x][y][z]`` grid.

    ``heights[z][x]`` is the absolute Y of that block (``None`` when the column is empty) and
    ``surface[z]`` labels the block with characters from ``surface_palette``.
    """
    sx, sy, sz = _server_grid_shape(grid)
    empty = AIR_LIKE | ignore
    heights: list[list[int | None]] = [[None] * sx for _ in range(sz)]
    tops: list[list[str | None]] = [[None] * sx for _ in range(sz)]
    for x in range(sx):
        for z in range(sz):
            for y in range(sy - 1, -1, -1):
                block = grid[x][y][z]
                if block not in empty:
                    heights[z][x] = y_origin + y
                    tops[z][x] = block
                    break
    counts = Counter(block for row in tops for block in row if block is not None)
    char_of = _assign_chars(counts, "Use a smaller area.")
    surface = ["".join(SKIP_CHAR if block is None else char_of[block] for block in row) for row in tops]
    return {
        "heights": heights,
        "surface_palette": {char: block for block, char in char_of.items()},
        "surface": surface,
    }
