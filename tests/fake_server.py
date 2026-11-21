"""An in-process fake of the MCPyLib plugin's TCP protocol (see MCPyLib docs/protocol.md).

Requests are newline-delimited JSON objects ``{"token", "action", "params"}``; every response is
``{"success", "data", "error"}`` followed by a newline. Connections are persistent, like the real
plugin. The fake keeps a little world state so that tools can be tested end to end, records every
authenticated request in ``requests``, and lets tests inject failures (``handlers``, ``delay``,
``garbage``).
"""

from __future__ import annotations

import base64
import json
import socket
import socketserver
import threading
import time
import uuid
import zlib
from collections.abc import Callable
from typing import Any

DEFAULT_TOKEN = "fake-token-Zq8dKX3vR9-do-not-log"


class FakeCommandError(Exception):
    """Raise from a handler to make the fake answer ``success: false`` with this message."""


def _block_id(name: str) -> str:
    if "invalid" in name:
        raise FakeCommandError(f"Invalid block type: {name}")
    name = name.lower()
    return name if name.startswith("minecraft:") else f"minecraft:{name.split(':')[-1]}"


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        fake: FakeMinecraftServer = self.server.fake  # type: ignore[attr-defined]
        fake._track(self.connection)
        try:
            for line in self.rfile:
                if not line.strip():
                    continue
                self.wfile.write(fake.handle_line(line))
                self.wfile.flush()
        except OSError:
            pass
        finally:
            fake._untrack(self.connection)


class _TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False


class FakeMinecraftServer:
    def __init__(self, token: str = DEFAULT_TOKEN) -> None:
        self.token = token
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}
        self.delay = 0.0
        self.garbage = False

        self.blocks: dict[tuple[int, int, int], str] = {}
        self.block_specs: dict[tuple[int, int, int], dict[str, Any]] = {}
        self.players: dict[str, dict[str, Any]] = {
            "Steve": {
                "uuid": "8667ba71-b85a-4004-af54-457a9734eed7",
                "pos": [10, 64, -20],
                "gamemode": "SURVIVAL",
                "level": 5,
                "points": 120,
                "progress": 0.25,
                "inventory": {
                    0: {"item": "minecraft:diamond_sword", "amount": 1, "enchantments": {"sharpness": 5}},
                    3: {"item": "minecraft:bread", "amount": 12},
                },
            },
            "Alex": {
                "uuid": "ec561538-f3fd-461d-aff5-086b22154bce",
                "pos": [-3, 70, 8],
                "gamemode": "CREATIVE",
                "level": 0,
                "points": 0,
                "progress": 0.0,
                "inventory": {},
            },
        }
        self.entities: dict[str, dict[str, Any]] = {}
        self.time = 1000
        self.gamerules = {"keep_inventory": "false", "mob_griefing": "true"}
        self.border = {
            "size": 60_000_000.0,
            "center_x": 0.0,
            "center_z": 0.0,
            "damage_amount": 0.2,
            "damage_buffer": 5.0,
            "warning_distance": 5,
            "warning_time": 15,
        }
        self.forced_chunks: set[tuple[int, int]] = set()
        self.bossbars: dict[str, dict[str, Any]] = {}
        self.teams: dict[str, dict[str, Any]] = {}
        self.objectives: dict[str, dict[str, Any]] = {}
        self.advancements: set[tuple[str, str]] = set()

        self._server: _TCPServer | None = None
        self._thread: threading.Thread | None = None
        self._connections: set[socket.socket] = set()
        self._lock = threading.Lock()
        self._port = 0

    # ------------------------------------------------------------------ lifecycle
    def start(self, port: int = 0) -> FakeMinecraftServer:
        self._server = _TCPServer(("127.0.0.1", port), _Handler)
        self._server.fake = self  # type: ignore[attr-defined]
        self._port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        with self._lock:
            connections = list(self._connections)
        for conn in connections:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None

    @property
    def port(self) -> int:
        return self._port

    def _track(self, conn: socket.socket) -> None:
        with self._lock:
            self._connections.add(conn)

    def _untrack(self, conn: socket.socket) -> None:
        with self._lock:
            self._connections.discard(conn)

    # ------------------------------------------------------------------ inspection helpers
    def actions(self) -> list[str]:
        return [action for action, _ in self.requests]

    def last(self, action: str | None = None) -> dict[str, Any]:
        for name, params in reversed(self.requests):
            if action is None or name == action:
                return params
        raise AssertionError(f"no {action or ''} request recorded; got {self.actions()}")

    def block_at(self, x: int, y: int, z: int) -> str:
        if (x, y, z) in self.blocks:
            return self.blocks[(x, y, z)]
        if y < 63:
            return "minecraft:stone"
        if y == 63:
            return "minecraft:grass_block"
        return "minecraft:air"

    # ------------------------------------------------------------------ protocol
    def handle_line(self, line: bytes) -> bytes:
        try:
            request = json.loads(line)
        except ValueError:
            return self._reply(False, error="Invalid JSON")
        if request.get("token") != self.token:
            return self._reply(False, error="Invalid token")
        action = str(request.get("action", ""))
        params = request.get("params") or {}
        with self._lock:
            self.requests.append((action, params))
        if self.delay:
            time.sleep(self.delay)
        if self.garbage:
            return b"<html>this is not the MCPyLib plugin</html>\n"
        key = action.lower()
        handler = self.handlers.get(key) or getattr(self, f"_do_{key}", None)
        try:
            data = handler(params) if handler else True
        except FakeCommandError as exc:
            return self._reply(False, error=str(exc))
        return self._reply(True, data=data)

    @staticmethod
    def _reply(success: bool, data: Any = None, error: str | None = None) -> bytes:
        return (json.dumps({"success": success, "data": data, "error": error}) + "\n").encode()

    def _player(self, name: str) -> dict[str, Any]:
        if name not in self.players:
            raise FakeCommandError(f"Player not found: {name}")
        return self.players[name]

    def _entity(self, entity_uuid: str) -> dict[str, Any]:
        if entity_uuid not in self.entities:
            raise FakeCommandError(f"Entity not found: {entity_uuid}")
        return self.entities[entity_uuid]

    # ------------------------------------------------------------------ blocks
    def _do_getblock(self, p: dict[str, Any]) -> str:
        return self.block_at(p["x"], p["y"], p["z"])

    def _do_setblock(self, p: dict[str, Any]) -> int:
        pos = (p["x"], p["y"], p["z"])
        self.blocks[pos] = _block_id(p["block"])
        if "block_state" in p or "nbt" in p:
            self.block_specs[pos] = {k: p[k] for k in ("block", "block_state", "nbt") if k in p}
        return 1

    def _corners(self, p: dict[str, Any]) -> tuple[range, range, range]:
        xs = range(min(p["x1"], p["x2"]), max(p["x1"], p["x2"]) + 1)
        ys = range(min(p["y1"], p["y2"]), max(p["y1"], p["y2"]) + 1)
        zs = range(min(p["z1"], p["z2"]), max(p["z1"], p["z2"]) + 1)
        return xs, ys, zs

    def _do_getblocks(self, p: dict[str, Any]) -> list[list[list[str]]]:
        xs, ys, zs = self._corners(p)
        return [[[self.block_at(x, y, z) for z in zs] for y in ys] for x in xs]

    def _do_fill(self, p: dict[str, Any]) -> int:
        block = _block_id(p["block"])
        xs, ys, zs = self._corners(p)
        for x in xs:
            for y in ys:
                for z in zs:
                    self.blocks[(x, y, z)] = block
        return len(xs) * len(ys) * len(zs)

    def _do_clone(self, p: dict[str, Any]) -> int:
        xs, ys, zs = self._corners(p)
        volume = len(xs) * len(ys) * len(zs)
        if volume > 32768:
            raise FakeCommandError(f"Region too large (max 32768 blocks): {volume}")
        snapshot = {(x, y, z): self.block_at(x, y, z) for x in xs for y in ys for z in zs}
        for (x, y, z), block in snapshot.items():
            self.blocks[(p["dest_x"] + x - xs.start, p["dest_y"] + y - ys.start, p["dest_z"] + z - zs.start)] = block
        return volume

    def _do_bulkedit(self, p: dict[str, Any]) -> int:
        x0, y0, z0 = p["x"], p["y"], p["z"]
        cells: list[tuple[int, int, int, Any]] = []
        if "encoding" in p:  # mcpylib >= 1.2.0: palette + RLE + zlib + base64
            if p["encoding"] != "palette_rle_zlib":
                raise FakeCommandError(f"Unsupported encoding: {p['encoding']}")
            sy, sz = p["sizeY"], p["sizeZ"]
            rle = zlib.decompress(base64.b64decode(p["data"])).decode()
            numbers = [int(v) for v in rle.split(",")] if rle else []
            flat: list[int] = []
            for i in range(0, len(numbers), 2):
                flat.extend([numbers[i + 1]] * numbers[i])
            for index, palette_index in enumerate(flat):
                cells.append((index // (sy * sz), (index // sz) % sy, index % sz, p["palette"][palette_index]))
        else:  # mcpylib 1.1.x: plain [x][y][z] array
            for dx, plane in enumerate(p["blocks"]):
                for dy, column in enumerate(plane):
                    for dz, value in enumerate(column):
                        cells.append((dx, dy, dz, value))
        placed = 0
        for dx, dy, dz, value in cells:
            if value is None:
                continue
            pos = (x0 + dx, y0 + dy, z0 + dz)
            if isinstance(value, dict):
                self.blocks[pos] = _block_id(value["block"])
                self.block_specs[pos] = value
            else:
                self.blocks[pos] = _block_id(value)
            placed += 1
        return placed

    # ------------------------------------------------------------------ players
    def _do_list(self, p: dict[str, Any]) -> dict[str, Any]:
        players = [{"name": n, "uuid": d["uuid"], "gamemode": d["gamemode"]} for n, d in self.players.items()]
        return {"online_count": len(players), "max_players": 20, "players": players}

    def _do_getpos(self, p: dict[str, Any]) -> list[int]:
        return list(self._player(p["username"])["pos"])

    def _do_teleport(self, p: dict[str, Any]) -> bool:
        self._player(p["username"])["pos"] = [int(p["x"]), int(p["y"]), int(p["z"])]
        return True

    def _do_gamemode(self, p: dict[str, Any]) -> bool:
        if p["mode"].upper() not in ("SURVIVAL", "CREATIVE", "ADVENTURE", "SPECTATOR"):
            raise FakeCommandError(f"Invalid gamemode: {p['mode']}")
        self._player(p["username"])["gamemode"] = p["mode"].upper()
        return True

    def _do_getitem(self, p: dict[str, Any]) -> dict[str, Any]:
        player = self._player(p["username"])
        if not 0 <= p["slot"] <= 40:
            raise FakeCommandError(f"Invalid slot: {p['slot']} (valid: 0-40)")
        return player["inventory"].get(p["slot"], {"item": None, "amount": 0})

    def _do_setitem(self, p: dict[str, Any]) -> bool:
        self._player(p["username"])["inventory"][p["slot"]] = {
            "item": _block_id(p["item"]),
            "amount": p["amount"],
        }
        return True

    def _do_experience(self, p: dict[str, Any]) -> dict[str, Any]:
        player = self._player(p["username"])
        if p["action"] == "add" and p.get("target") == "levels":
            player["level"] += p["amount"]
        elif p["action"] == "add":
            player["points"] += p["amount"]
        elif p["action"] == "set" and p.get("target") == "levels":
            player["level"] = p["amount"]
        return {"level": player["level"], "points": player["points"], "progress": player["progress"]}

    def _do_advancement(self, p: dict[str, Any]) -> bool:
        key = (p["username"], p["advancement"])
        self._player(p["username"])
        if p["action"] == "grant":
            self.advancements.add(key)
        elif p["action"] == "revoke":
            self.advancements.discard(key)
        else:
            return key in self.advancements
        return True

    def _do_clear(self, p: dict[str, Any]) -> int:
        player = self._player(p["username"])
        removed = sum(stack["amount"] for stack in player["inventory"].values())
        player["inventory"] = {}
        return removed

    # ------------------------------------------------------------------ world
    def _do_time(self, p: dict[str, Any]) -> int:
        if p["action"] == "set":
            if not 0 <= p["value"] <= 24000:
                raise FakeCommandError(f"Value out of range: {p['value']} (valid: 0-24000)")
            self.time = p["value"]
        elif p["action"] == "add":
            self.time = (self.time + p["value"]) % 24000
        return self.time

    def _do_gamerule(self, p: dict[str, Any]) -> str:
        if p["rule"] not in self.gamerules:
            raise FakeCommandError(f"Invalid game rule: {p['rule']}")
        if p.get("value") is not None:
            self.gamerules[p["rule"]] = p["value"]
        return self.gamerules[p["rule"]]

    def _do_worldborder(self, p: dict[str, Any]) -> dict[str, Any]:
        action = p["action"]
        if action == "get":
            return dict(self.border)
        if action == "set":
            self.border["size"] = float(p["value"])
            return {"size": self.border["size"]}
        if action == "add":
            self.border["size"] += float(p["value"])
            return {"size": self.border["size"]}
        if action == "center":
            self.border["center_x"], self.border["center_z"] = float(p["x"]), float(p["z"])
            return {"center_x": self.border["center_x"], "center_z": self.border["center_z"]}
        if action == "damage":
            self.border["damage_amount"] = float(p.get("value", self.border["damage_amount"]))
            return {"damage_amount": self.border["damage_amount"]}
        if action == "warning":
            self.border["warning_distance"] = int(p.get("value", self.border["warning_distance"]))
            self.border["warning_time"] = int(p.get("time", self.border["warning_time"]))
            return {
                "warning_distance": self.border["warning_distance"],
                "warning_time": self.border["warning_time"],
            }
        raise FakeCommandError(f"Invalid action: {action}")

    def _do_forceload(self, p: dict[str, Any]) -> bool:
        chunk = (p["x"] >> 4, p["z"] >> 4)
        if p["action"] == "add":
            self.forced_chunks.add(chunk)
        elif p["action"] == "remove":
            self.forced_chunks.discard(chunk)
        else:
            return chunk in self.forced_chunks
        return True

    def _do_locate(self, p: dict[str, Any]) -> dict[str, Any]:
        if p["structure"].endswith("unicorn_castle"):
            return {"found": False}
        return {"found": True, "x": 256, "y": 64, "z": -128}

    def _do_loot(self, p: dict[str, Any]) -> int:
        return 3

    # ------------------------------------------------------------------ entities
    def _do_summon(self, p: dict[str, Any]) -> str:
        entity_uuid = str(uuid.uuid4())
        self.entities[entity_uuid] = {
            "type": "minecraft:" + p["entity_type"].removeprefix("minecraft:"),
            "pos": [p["x"], p["y"], p["z"]],
            "yaw": 0.0,
            "pitch": 0.0,
            "tags": set(),
        }
        return entity_uuid

    def _do_kill(self, p: dict[str, Any]) -> int:
        selector = p["selector"]
        if selector.startswith("player:"):
            self._player(selector.removeprefix("player:"))
            return 1
        if selector == "all":
            doomed = list(self.entities)
        else:
            wanted = "minecraft:" + selector.removeprefix("minecraft:")
            doomed = [u for u, e in self.entities.items() if e["type"] == wanted]
        for entity_uuid in doomed:
            del self.entities[entity_uuid]
        return len(doomed)

    def _do_getentitypos(self, p: dict[str, Any]) -> dict[str, Any]:
        e = self._entity(p["uuid"])
        return {"x": e["pos"][0], "y": e["pos"][1], "z": e["pos"][2], "yaw": e["yaw"], "pitch": e["pitch"]}

    def _do_getentitystatus(self, p: dict[str, Any]) -> dict[str, Any]:
        e = self._entity(p["uuid"])
        return {
            "uuid": p["uuid"],
            "type": e["type"],
            "custom_name": None,
            "is_valid": True,
            "is_dead": False,
            "world": "world",
            "position": {"x": e["pos"][0], "y": e["pos"][1], "z": e["pos"][2]},
            "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "health": 20.0,
            "max_health": 20.0,
            "has_ai": True,
        }

    def _do_removeentity(self, p: dict[str, Any]) -> bool:
        self._entity(p["uuid"])
        del self.entities[p["uuid"]]
        return True

    def _do_addtag(self, p: dict[str, Any]) -> bool:
        tags = self._entity(p["uuid"])["tags"]
        added = p["tag"] not in tags
        tags.add(p["tag"])
        return added

    def _do_removetag(self, p: dict[str, Any]) -> bool:
        tags = self._entity(p["uuid"])["tags"]
        removed = p["tag"] in tags
        tags.discard(p["tag"])
        return removed

    def _do_gettags(self, p: dict[str, Any]) -> list[str]:
        return sorted(self._entity(p["uuid"])["tags"])

    # ------------------------------------------------------------------ scoreboard
    def _do_team(self, p: dict[str, Any]) -> dict[str, Any]:
        action = p["action"]
        if action == "list":
            return {
                "teams": [
                    {
                        "name": n,
                        "display_name": t["display_name"],
                        "members": sorted(t["members"]),
                        "size": len(t["members"]),
                    }
                    for n, t in self.teams.items()
                ]
            }
        name = p["name"]
        if action == "add":
            if name in self.teams:
                raise FakeCommandError(f"Team already exists: {name}")
            self.teams[name] = {"display_name": p.get("display_name", name), "members": set(), "options": {}}
            return {"name": name}
        if name not in self.teams:
            raise FakeCommandError(f"Team not found: {name}")
        team = self.teams[name]
        if action == "remove":
            del self.teams[name]
            return {"removed": True}
        if action == "join":
            team["members"].update(p["members"])
            return {"added": len(p["members"])}
        if action == "leave":
            team["members"].difference_update(p["members"])
            return {"removed_count": len(p["members"])}
        if action == "modify":
            team["options"][p["option"]] = p["value"]
            return {"modified": True}
        raise FakeCommandError(f"Invalid action: {action}")

    def _do_bossbar(self, p: dict[str, Any]) -> dict[str, Any]:
        action, bar_id = p["action"], p["id"]
        if action == "list":
            return {"bars": list(self.bossbars)}
        if action == "add":
            if bar_id in self.bossbars:
                raise FakeCommandError(f"BossBar already exists: {bar_id}")
            self.bossbars[bar_id] = {
                "title": p.get("title", bar_id),
                "color": p.get("color", "WHITE"),
                "style": p.get("style", "SOLID"),
                "progress": p.get("progress", 1.0),
                "visible": p.get("visible", True),
                "players": [],
            }
            return {"id": bar_id}
        if bar_id not in self.bossbars:
            raise FakeCommandError(f"BossBar not found: {bar_id}")
        bar = self.bossbars[bar_id]
        if action == "remove":
            del self.bossbars[bar_id]
            return {"removed": True}
        if action == "set":
            for key in ("title", "color", "style", "progress", "visible"):
                if key in p:
                    bar[key] = p[key]
            return {"updated": True}
        if action == "addplayer":
            self._player(p["username"])
            bar["players"].append(p["username"])
            return {"added": True}
        if action == "removeplayer":
            bar["players"].remove(p["username"])
            return {"removed": True}
        if action == "get":
            return {"id": bar_id, **bar}
        raise FakeCommandError(f"Invalid action: {action}")

    def _do_getscore(self, p: dict[str, Any]) -> int:
        if p["objective"] not in self.objectives:
            raise FakeCommandError(f"Objective not found: {p['objective']}")
        return self.objectives[p["objective"]]["scores"].get(p["player"], 0)

    def _do_setscore(self, p: dict[str, Any]) -> bool:
        if p["objective"] not in self.objectives:
            raise FakeCommandError(f"Objective not found: {p['objective']}")
        self.objectives[p["objective"]]["scores"][p["player"]] = p["score"]
        return True

    def _do_addobjective(self, p: dict[str, Any]) -> bool:
        if p["name"] in self.objectives:
            raise FakeCommandError(f"Objective already exists: {p['name']}")
        self.objectives[p["name"]] = {"criteria": p["criteria"], "scores": {}}
        return True
