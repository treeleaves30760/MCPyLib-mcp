# MCPyLib-mcp

[![CI](https://github.com/treeleaves30760/MCPyLib-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/treeleaves30760/MCPyLib-mcp/actions/workflows/ci.yml)

An [MCP](https://modelcontextprotocol.io) server that lets AI agents such as Claude Code, Claude Desktop,
Cursor and VS Code control a Minecraft server through [MCPyLib](https://github.com/treeleaves30760/MCPyLib).
Agents can build structures, survey terrain, and manage players, entities, the world, chat and scoreboards.

[繁體中文說明](README.zh-TW.md)

```text
MCP client ──(MCP: stdio or HTTP)──> mcpylib-mcp ──(MCPyLib protocol: TCP 65535 + token)──> MCPyLib plugin
(Claude, Cursor, VS Code...)          (this project)                                     on Paper/Spigot
```

Once it is connected, you can ask things like:

- "Who is online, and where is Steve?"
- "Build a small oak cabin with a porch next to Steve."
- "Survey 30 blocks around spawn and tell me where the flattest spot is."
- "Make it night, start a thunderstorm and give everyone night vision."

## Features

- **86 tools covering the whole MCPyLib client API.** They are organised in seven groups. Every tool has
  typed, validated parameters and returns structured JSON. MCP annotations mark each tool as read-only,
  destructive or idempotent, so clients can auto-approve reads and ask before destructive changes.
- **Block tools designed for language models.** `get_blocks` returns a region as text layers (floor plans
  stacked bottom to top). `build_from_layers` accepts the same format, so an agent can read, edit and write
  back a build. `get_height_map` finds the ground in one call.
- **Safety controls:**
  - a per-call block limit;
  - a read-only mode;
  - tool allowlists and denylists (by name, glob or group);
  - the token is never logged.
- **Resources and prompts:** a live server-status resource, player lookups and a building guide, plus
  "build a structure" and "survey an area" prompts.
- **stdio and streamable HTTP transports.**

## Requirements

- A Paper or Spigot server running Minecraft 26.1 or newer (Java 25) with the
  [MCPyLib plugin](https://github.com/treeleaves30760/MCPyLib) 1.2.0 or newer (1.2.2 recommended).
- [uv](https://docs.astral.sh/uv/getting-started/installation/), which provides `uvx`. If you don't use
  uv, you need Python 3.11+ and pip.

## Quick start

1. **Install the plugin.** Put the MCPyLib plugin jar from the
   [MCPyLib releases](https://github.com/treeleaves30760/MCPyLib/releases) into the server's `plugins/` folder
   and restart the server.
2. **Get a token.** Run `/mcpylib token` in the server console, or in game with the `mcpylib.admin`
   permission. Copy the token it prints.
3. **Check that the MCP server runs.** This needs no token and does not connect to Minecraft:

   ```bash
   uvx mcpylib-mcp --list-tools
   ```

4. **Add it to your MCP client** using one of the configurations below, then ask your agent who is online.

`uvx` downloads the server from PyPI and caches it the first time it runs. Add `--refresh` once to pick up a
new release, or pin one with `uvx mcpylib-mcp@0.1.0`.

If you prefer pip, run `pip install mcpylib-mcp`. That installs the `mcpylib-mcp` command.

## Connect your MCP client

In every example, replace `<token>` with your token. If Minecraft runs on a different machine, also set
`MCPYLIB_HOST`. If you changed the plugin's port, set `MCPYLIB_PORT` too.

### Claude Code

```bash
claude mcp add mcpylib -e MCPYLIB_TOKEN=<token> -- uvx mcpylib-mcp
```

- **Remote server:** add `-e MCPYLIB_HOST=192.168.1.20`.
- **All projects:** add `--scope user` before `mcpylib`.
- **Check the connection:** run `claude mcp list` or use `/mcp` in a session.

**Shared projects.** To share the server in a project, add a `.mcp.json` file that reads the token from your
environment. This keeps the token out of the repository:

```json
{
  "mcpServers": {
    "mcpylib": {
      "command": "uvx",
      "args": ["mcpylib-mcp"],
      "env": { "MCPYLIB_TOKEN": "${MCPYLIB_TOKEN}" }
    }
  }
}
```

### Claude Desktop

1. Open the config file with **Settings > Developer > Edit Config**. The file is
   `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS and
   `%APPDATA%\Claude\claude_desktop_config.json` on Windows.
2. Add the server:

   ```json
   {
     "mcpServers": {
       "mcpylib": {
         "command": "uvx",
         "args": ["mcpylib-mcp"],
         "env": {
           "MCPYLIB_TOKEN": "<token>",
           "MCPYLIB_HOST": "localhost",
           "MCPYLIB_PORT": "65535"
         }
       }
     }
   }
   ```

3. Restart Claude Desktop.

If Claude Desktop cannot find `uvx`, for example with a `spawn uvx ENOENT` error, put the full path in
`command`. Get it from `which uvx` on macOS or Linux, or `where uvx` on Windows.

### Cursor

Add the server to `~/.cursor/mcp.json` to use it in every project, or to `.cursor/mcp.json` for one project:

```json
{
  "mcpServers": {
    "mcpylib": {
      "command": "uvx",
      "args": ["mcpylib-mcp"],
      "env": { "MCPYLIB_TOKEN": "<token>" }
    }
  }
}
```

### VS Code

Add the server to `.vscode/mcp.json` in your workspace. For every workspace, use **MCP: Open User
Configuration** instead. With this configuration, VS Code asks for the token the first time the server starts,
so the token is not written into the file:

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "mcpylib-token",
      "description": "MCPyLib token (run /mcpylib token on the Minecraft server)",
      "password": true
    }
  ],
  "servers": {
    "mcpylib": {
      "type": "stdio",
      "command": "uvx",
      "args": ["mcpylib-mcp"],
      "env": { "MCPYLIB_TOKEN": "${input:mcpylib-token}" }
    }
  }
}
```

### Other clients, and streamable HTTP

Any client that launches stdio servers works the same way. Use the command
`uvx mcpylib-mcp` with `MCPYLIB_TOKEN` set in its
environment.

Some clients connect to a URL instead. Streamable HTTP also lets several clients share one server process.
To use it, start the server yourself:

```bash
MCPYLIB_TOKEN=<token> uvx mcpylib-mcp --transport http --port 8000
```

In PowerShell, run `$env:MCPYLIB_TOKEN = "<token>"` first. Then point each client at
`http://127.0.0.1:8000/mcp`:

- **Claude Code:** `claude mcp add --transport http mcpylib http://127.0.0.1:8000/mcp`
- **VS Code:** `"mcpylib": { "type": "http", "url": "http://127.0.0.1:8000/mcp" }`
- **Cursor:** `"mcpylib": { "url": "http://127.0.0.1:8000/mcp" }`

The HTTP endpoint has no authentication of its own; read [Safety](#safety) before exposing it.

## Configuration

Settings come from environment variables. Command-line flags of the same name take precedence.

| Variable | Flag | Default | Meaning |
| --- | --- | --- | --- |
| `MCPYLIB_TOKEN` | `--token` | required | Token printed by `/mcpylib token`. Prefer the variable, because other local users can see command lines. |
| `MCPYLIB_HOST` | `--mc-host` | `localhost` | Host of the Minecraft server that runs the MCPyLib plugin. |
| `MCPYLIB_PORT` | `--mc-port` | `65535` | Plugin port (`server.port` in `plugins/MCPyLib/config.yml`). |
| `MCPYLIB_TIMEOUT` | `--timeout` | `30` | Seconds to wait for each reply from the plugin. |
| `MCPYLIB_MAX_BLOCKS` | `--max-blocks` | `100000` | The most blocks one tool call may read or change. |
| `MCPYLIB_READ_ONLY` | `--read-only` / `--no-read-only` | `false` | Register only tools that do not change the world. |
| `MCPYLIB_ALLOWED_TOOLS` | `--allow-tools` | all tools | Register only these tools. Entries are names, globs (`get_*`) or groups (`group:blocks`). |
| `MCPYLIB_DENIED_TOOLS` | `--deny-tools` | none | Never register these tools. Same syntax; the denylist wins over the allowlist. |
| `MCPYLIB_TRANSPORT` | `--transport` | `stdio` | `stdio`, or `http` for streamable HTTP. |
| `MCPYLIB_HTTP_HOST` | `--host` | `127.0.0.1` | Address the HTTP transport binds to. |
| `MCPYLIB_HTTP_PORT` | `--port` | `8000` | Port of the HTTP transport. The endpoint is `/mcp`. |
| `MCPYLIB_LOG_LEVEL` | `--log-level` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. Logs go to stderr. |

- `--mc-host` and `--mc-port` point at Minecraft. `--host` and `--port` configure the MCP HTTP transport.
- Lists are separated by commas or spaces. Booleans accept `true`/`false`, `1`/`0`, `yes`/`no` and
  `on`/`off`.
- `--list-tools` prints the tools your settings enable and exits. It needs no token, so it is a quick way to
  check a filter. `--version` and `--help` work the same way.

Examples:

```bash
# Let an agent look around but change nothing
mcpylib-mcp --read-only

# Building only: block tools plus player positions, never run_command
MCPYLIB_ALLOWED_TOOLS="group:blocks get_players get_player_position" mcpylib-mcp

# Everything except raw console commands and mass entity removal
MCPYLIB_DENIED_TOOLS=run_command,kill_entities mcpylib-mcp
```

## Tools

Tool groups: `server`, `blocks`, `players`, `world`, `entities`, `chat` and `scoreboard`. The
**Access** column means:

- **read-only:** never changes the world. These tools stay available in read-only mode.
- **destructive:** can overwrite or delete things that cannot be restored.
- **changes:** modifies the world without destroying anything.

Coordinates follow Minecraft: +X is east, +Z is south and +Y is up. Block, world and particle tools act on
the server's main world.

### server

| Tool | What it does | Access |
| --- | --- | --- |
| `get_players` | List online players (name, UUID, game mode) and the player limit. | read-only |
| `run_command` | Run any Minecraft command as the server console. The block limit does not apply; see [Safety](#safety). | destructive |

### blocks

| Tool | What it does | Access |
| --- | --- | --- |
| `get_block` | Return the block id at one position, e.g. `minecraft:stone`. | read-only |
| `get_blocks` | Read every block in a box, as text layers, an index array or block counts. | read-only |
| `get_height_map` | For each column of an area, the Y of the highest non-air block, optionally ignoring leaves or plants. | read-only |
| `set_block` | Place one block, with optional block state and sign text, replacing what is there. | destructive |
| `fill_region` | Fill a box with one block; use `air` to clear an area. | destructive |
| `clone_region` | Copy a box of blocks to another place (at most 32,768 blocks, a plugin limit). | destructive |
| `edit_blocks` | Place many different blocks in one call from a 3D array (MCPyLib's bulk edit). | destructive |
| `build_from_layers` | Build from text layers: floor plans stacked bottom to top, each character one block. | destructive |

### players

| Tool | What it does | Access |
| --- | --- | --- |
| `get_player_position` | Block position of an online player's feet. | read-only |
| `teleport_player` | Teleport a player, optionally setting where they face. | changes |
| `set_gamemode` | Set a player's game mode. | changes |
| `give_item` | Add items to a player's inventory. | changes |
| `get_inventory` | List a player's non-empty inventory slots with items, amounts and enchantments. | read-only |
| `set_inventory_slot` | Put an item stack into one slot, replacing what was there. | destructive |
| `clear_inventory` | Remove all items, or one item type, from a player's inventory. | destructive |
| `enchant_held_item` | Enchant the item in a player's main hand. | changes |
| `apply_effect` | Give a player a status effect such as speed or night vision. | changes |
| `clear_effects` | Remove one or all status effects. | changes |
| `get_experience` | A player's level, points and progress to the next level. | read-only |
| `update_experience` | Add or set experience points or levels. | changes |
| `set_spawnpoint` | Set where a player respawns. | changes |
| `get_advancement` | Whether a player has completed an advancement. | read-only |
| `set_advancement` | Grant or revoke an advancement. | destructive |
| `spread_players` | Teleport players to random surface positions around a point (`/spreadplayers`). | changes |

### world

| Tool | What it does | Access |
| --- | --- | --- |
| `get_time` | Time of day: ticks, phase (day, sunset, night, sunrise) and clock time. | read-only |
| `set_time` | Set or advance the time, by preset (`day`, `noon`, `night`...) or ticks. | changes |
| `set_weather` | Clear, rain or thunder, optionally for a duration. | changes |
| `set_difficulty` | Set the difficulty. | changes |
| `get_gamerule` | Current value of a game rule. | read-only |
| `set_gamerule` | Set a game rule and return the value the server now reports. | changes |
| `set_world_spawn` | Set the world spawn point. | changes |
| `set_default_gamemode` | Set the game mode new players get. | changes |
| `get_world_border` | The world border's size, centre, damage and warning settings. | read-only |
| `set_world_border` | Change any combination of world-border settings in one call. | changes |
| `get_chunk_force_loaded` | Whether the chunk containing a block is force-loaded. | read-only |
| `set_chunk_force_loaded` | Force-load a chunk, or stop force-loading it. | changes |
| `fill_biome` | Change the biome of a box. | destructive |
| `locate_structure` | Find the nearest structure of a type, such as a village. | read-only |
| `place_feature` | Generate a feature (tree, ore vein...) as world generation does. | destructive |
| `place_structure` | Generate a whole structure (village, temple...). | destructive |
| `place_jigsaw` | Generate a jigsaw structure from a template pool. | destructive |
| `place_template` | Place a saved structure template. | destructive |
| `spawn_loot` | Roll a loot table and drop the items at a position. | changes |

### entities

| Tool | What it does | Access |
| --- | --- | --- |
| `summon_entity` | Spawn an entity and return its UUID, which the other entity tools use. | changes |
| `kill_entities` | Remove entities by type, a player, or all non-player entities (at most 1,000 per call). | destructive |
| `remove_entity` | Delete one entity without drops. | destructive |
| `get_entity` | An entity's type, name, position, rotation, velocity, health and AI state. | read-only |
| `teleport_entity` | Move an entity to an exact position. | changes |
| `set_entity_velocity` | Push an entity by setting its velocity vector. | changes |
| `set_entity_rotation` | Turn an entity without moving it. | changes |
| `set_entity_ai` | Turn a mob's AI on or off. | changes |
| `set_entity_target` | Make a mob attack an entity, or clear its target. | changes |
| `get_entity_equipment` | Items in an entity's armour and hand slots. | read-only |
| `set_entity_equipment` | Equip a mob or armor stand, with optional drop chances. | destructive |
| `damage_entity` | Hurt a living entity. | destructive |
| `ride_entity` | Make one entity ride another, or dismount it. | changes |
| `get_entity_attribute` | Base and effective value of an attribute, e.g. `max_health`. | read-only |
| `set_entity_attribute` | Set an attribute's base value, e.g. `scale` 2. | changes |
| `get_entity_tags` | An entity's scoreboard tags. | read-only |
| `update_entity_tags` | Add and remove scoreboard tags. | changes |
| `get_villager` | A villager's profession, level and trades. | read-only |
| `set_villager_profession` | Change a villager's profession, which resets its trades. | destructive |
| `set_villager_trades` | Replace all of a villager's trades. | destructive |

### chat

| Tool | What it does | Access |
| --- | --- | --- |
| `broadcast_message` | Send a chat message to every player. | changes |
| `send_message` | Send a private message to one player. | changes |
| `send_rich_message` | Send formatted, clickable text with `/tellraw`. | changes |
| `show_title` | Show a title and subtitle on a player's screen. | changes |
| `play_sound` | Play a sound to a player. | changes |
| `stop_sound` | Stop one sound, or all sounds, for a player. | changes |
| `spawn_particles` | Show particles at a position. | changes |

### scoreboard

| Tool | What it does | Access |
| --- | --- | --- |
| `create_objective` | Create a scoreboard objective. | changes |
| `remove_objective` | Delete an objective and all of its scores. | destructive |
| `set_objective_display` | Show an objective in the sidebar, below names or in the list, or clear a slot. | changes |
| `set_score` | Set a score, replacing the previous value. | destructive |
| `get_score` | Read a score. | read-only |
| `list_teams` | All teams with display names and members. | read-only |
| `create_team` | Create a team. | changes |
| `remove_team` | Delete a team. | destructive |
| `update_team_members` | Add and remove team members. | changes |
| `set_team_option` | Change a team option such as colour or friendly fire. | changes |
| `list_bossbars` | Boss bars created through MCPyLib, with their settings and viewers. | read-only |
| `create_bossbar` | Create a boss bar and show it to players. | changes |
| `update_bossbar` | Change a boss bar's title, colour, style, progress or viewers. | changes |
| `remove_bossbar` | Delete a boss bar. | destructive |

### The layers format

`get_blocks` (with the default `layout="layers"`) and `build_from_layers` share one format:

- **Palette:** maps single characters to blocks.
- **Layers:** a list of horizontal slices, ordered bottom to top.
  - Each slice is a list of rows, ordered north to south.
  - Each row is a string read west to east, one character per block.
- **Special characters:** `.` is air and a space leaves the existing block unchanged.

This call builds a 3x3 stone-brick ring with a glass ring on top:

```json
{
  "x": 100, "y": 64, "z": -20,
  "palette": { "#": "stone_bricks", "G": "glass" },
  "layers": [
    ["###", "#.#", "###"],
    ["#G#", "G.G", "#G#"]
  ]
}
```

A palette entry can also be an object with a block state, for example
`{"block": "oak_door", "block_state": {"half": "lower", "facing": "south"}}`. The
`minecraft://guide/building` resource explains the format and a building workflow in more detail.

## Resources and prompts

| Resource | Contents |
| --- | --- |
| `minecraft://server/status` | Connection state, online players, time of day, world border, and this server's limits and enabled tools. It reports `connected: false` with the reason when the plugin is unreachable. |
| `minecraft://players/{username}` | An online player's UUID, game mode, position and experience. |
| `minecraft://guide/building` | Coordinates, block states, the layers format and a building workflow (Markdown). |

| Prompt | What it does |
| --- | --- |
| `build_structure` | Plans and builds a described structure. It surveys the site, prepares the ground, builds in sections, verifies the result and reports. Hidden when the tools it needs are disabled, as in read-only mode. |
| `survey_area` | Inspects an area without changing it: terrain heights, materials, water, player builds and good building spots. |

## Safety

The MCPyLib token gives full control of the Minecraft server. Treat this MCP server as an operator account.

- **Per-call block limit.** `MCPYLIB_MAX_BLOCKS` (default 100,000) caps the region of every block tool:
  `get_blocks`, `get_height_map`, `fill_region`, `clone_region`, `edit_blocks`, `build_from_layers` and
  `fill_biome`. The size is checked before anything is sent, so an over-sized request never reaches
  Minecraft and the agent is told to split the work. The limit does not cover `run_command`, or world
  generation (`place_structure` and the other `place_*` tools), whose size the game decides.
- **Read-only mode.** `--read-only` or `MCPYLIB_READ_ONLY=true` registers only the 21 read-only tools.
  Write tools are not just refused: the client never sees them. Allowlists cannot add write tools back.
- **Allowlists and denylists.** They are applied when the server starts. An entry that matches no tool is a
  startup error, so a typo such as `run_comand` can never silently leave a tool enabled. Use `--list-tools`
  to preview the result.
- **`run_command`** runs any console command, including `/stop` and `/op`, and bypasses the limits above.
  Deny it (`MCPYLIB_DENIED_TOOLS=run_command`) if you want the other safety settings to mean something.
- **Annotations.** Every tool declares MCP annotations: `readOnlyHint`, `destructiveHint`, `idempotentHint`
  and `openWorldHint: false`. Clients that honour them can auto-approve read-only tools and ask before
  destructive ones. Keep approval prompts on for destructive tools when working on a world you care about.
- **Token handling.** Keep the token in `MCPYLIB_TOKEN` rather than `--token`, because other local users can
  read command lines. The server never logs it: settings print it as `***` and log output is filtered as a
  second line of defence. If a token leaks, replace it with `/mcpylib token regenerate`, then update your
  MCP configuration.
- **HTTP transport.** The HTTP endpoint has no authentication. By default it binds to `127.0.0.1`, and the
  MCP SDK then also enables DNS-rebinding protection. Binding to another address logs a warning, because
  anyone who can reach the port can control your Minecraft server. To serve it remotely, put it behind an
  authenticating reverse proxy, VPN or SSH tunnel.
- **Retries.** If the plugin does not answer in time, mcpylib retries the command once. After a timeout, a
  non-idempotent action such as `give_item` may therefore have happened twice. Check before repeating it.
- **Connections.** Each mcpylib-mcp process keeps one connection to the plugin. The plugin accepts
  `server.max-connections` connections at a time (default 10).

## Troubleshooting

| Message | What to do |
| --- | --- |
| `no MCPyLib token configured` | Set `MCPYLIB_TOKEN` in the client's `env` block. |
| `Authentication failed ... rejected the token` | The token is wrong or was regenerated. Run `/mcpylib token` to see the current token and update the configuration. |
| `Cannot reach the MCPyLib plugin at host:port` | Check that the Minecraft server is running, the plugin is loaded, `MCPYLIB_HOST`/`MCPYLIB_PORT` are right, and no firewall blocks the port. |
| `Timed out after 30s ...` | The server is busy or the request is large. Use smaller regions, or raise `MCPYLIB_TIMEOUT`. |
| `... more than the per-call limit ...` | Split the region into smaller parts. Only raise `MCPYLIB_MAX_BLOCKS` if a change that large is really intended. |
| The client shows no tools | Run the command from your configuration in a terminal with `--list-tools`, and check your allow/deny settings. For Claude Desktop, check that `uvx` is found (use its full path). |

Set `MCPYLIB_LOG_LEVEL=DEBUG` to see each call to the plugin in the client's MCP log.

## The mcpylib dependency

This server talks to the plugin through MCPyLib's Python client, [`mcpylib`](https://pypi.org/project/mcpylib/),
and depends on **`mcpylib>=1.2.2`** from PyPI.

- **Plugin compatibility:** mcpylib 1.2.x sends bulk edits in a compressed form that needs plugin 1.2.0 or
  newer for `edit_blocks` and `build_from_layers`. Plugin 1.2.1 adds doors and beds in `edit_blocks`, and
  1.2.2 rejects block states a block doesn't have, so use the latest plugin.
- **Why not a git dependency:** PyPI rejects packages whose dependencies are direct URLs.

## Development

```bash
git clone https://github.com/treeleaves30760/MCPyLib-mcp
cd MCPyLib-mcp
uv sync                       # create .venv with the dev tools
uv run pytest                 # tests run against a fake in-process MCPyLib plugin
uv run ruff check . && uv run ruff format --check .
uv run mcpylib-mcp --list-tools
```

The tests need no Minecraft server. `tests/fake_server.py` speaks the MCPyLib protocol over TCP, and the
suite drives the real MCP server in-process, over stdio and over HTTP.

Project layout:

- `src/mcpylib_mcp/tools/` defines one module per tool group.
- `bridge.py` serialises plugin calls and translates errors.
- `safety.py` holds the block limit and tool filtering.
- `encoding.py` implements the layers format.

## Related projects

- [MCPyLib](https://github.com/treeleaves30760/MCPyLib): the Python library and the Spigot/Paper plugin.
- [MCPyLib-skills](https://github.com/treeleaves30760/MCPyLib-skills): Agent Skills that teach AI coding
  agents the MCPyLib API, building recipes and mini-game patterns.
- [MCPyLib website](https://treeleaves30760.github.io/MCPyLib-website/): documentation and showcase.

## License

[MCPyLib Non-Commercial License](LICENSE), the same license as MCPyLib. Non-commercial use only; read the
license for details.
