# MCPyLib-mcp

[English](README.md)

MCPyLib-mcp 是一個 [MCP](https://modelcontextprotocol.io) 伺服器，透過 [MCPyLib](https://github.com/treeleaves30760/MCPyLib)
讓 AI 代理（Claude Code、Claude Desktop、Cursor、VS Code 等）控制 Minecraft 伺服器。代理可以蓋建築、勘查地形，也能管理玩家、實體、世界、聊天與計分板。

- **86 個工具，涵蓋完整的 MCPyLib API。**每個工具都有型別化參數並回傳結構化 JSON，也標註了唯讀、破壞性等 MCP annotations。
- **適合語言模型的方塊工具。**`get_blocks` 把區域讀成「文字圖層」，`build_from_layers` 用相同格式建造，`get_height_map` 一次找出地面高度。
- **安全機制：**
  - 每次呼叫的方塊數量上限；
  - 唯讀模式；
  - 工具允許清單與拒絕清單；
  - 絕不記錄 token。
- **Resources 與 prompts**（伺服器狀態、建造指南、建造與勘查），支援 stdio 與 streamable HTTP 兩種傳輸方式。

## 需求

- Paper 或 Spigot 伺服器，Minecraft 26.1 以上（Java 25），並安裝 MCPyLib 插件 1.2.0 以上（建議 1.2.2）。
- [uv](https://docs.astral.sh/uv/getting-started/installation/)，它提供 `uvx`。

## 快速開始

1. 從 [MCPyLib releases](https://github.com/treeleaves30760/MCPyLib/releases) 下載插件 jar，放進伺服器的 `plugins/` 資料夾，然後重新啟動伺服器。
2. 在伺服器主控台執行 `/mcpylib token`，複製顯示的 token。在遊戲內執行也可以，但需要 `mcpylib.admin` 權限。
3. 確認可以執行。這一步不需要 token，也不會連線到 Minecraft：

   ```bash
   uvx --from git+https://github.com/treeleaves30760/MCPyLib-mcp mcpylib-mcp --list-tools
   ```

4. 依下方說明加入你的 MCP 客戶端。

### Claude Code

```bash
claude mcp add mcpylib -e MCPYLIB_TOKEN=<token> -- uvx --from git+https://github.com/treeleaves30760/MCPyLib-mcp mcpylib-mcp
```

### Claude Desktop 與 Cursor

Claude Desktop 的設定檔是 `claude_desktop_config.json`，Cursor 的是 `~/.cursor/mcp.json`。兩者都使用以下格式：

```json
{
  "mcpServers": {
    "mcpylib": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/treeleaves30760/MCPyLib-mcp", "mcpylib-mcp"],
      "env": { "MCPYLIB_TOKEN": "<token>", "MCPYLIB_HOST": "localhost" }
    }
  }
}
```

如果 Claude Desktop 找不到 `uvx`，請把 `command` 改成 `uvx` 的完整路徑。

### VS Code

VS Code 的設定檔是 `.vscode/mcp.json`，格式與上面不同：最上層用 `servers`，並以 `"type": "stdio"` 指定傳輸方式。完整範例請見[英文說明](README.md#vs-code)。

### HTTP 模式

執行 `mcpylib-mcp --transport http --port 8000`，然後讓客戶端連到 `http://127.0.0.1:8000/mcp`。HTTP 端點本身沒有驗證機制，請只綁定在本機。

## 設定

命令列參數的優先順序高於環境變數。

| 環境變數 | 參數 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `MCPYLIB_TOKEN` | `--token` | 必填 | `/mcpylib token` 顯示的 token。建議用環境變數設定。 |
| `MCPYLIB_HOST` | `--mc-host` | `localhost` | Minecraft 伺服器位址 |
| `MCPYLIB_PORT` | `--mc-port` | `65535` | MCPyLib 插件連接埠 |
| `MCPYLIB_TIMEOUT` | `--timeout` | `30` | 等待插件回應的秒數 |
| `MCPYLIB_MAX_BLOCKS` | `--max-blocks` | `100000` | 單次呼叫可讀取或修改的方塊上限 |
| `MCPYLIB_READ_ONLY` | `--read-only` | `false` | 只註冊不會改變世界的工具 |
| `MCPYLIB_ALLOWED_TOOLS` | `--allow-tools` | 全部 | 只啟用這些工具（名稱、`get_*` 這類萬用字元，或 `group:blocks` 這類群組） |
| `MCPYLIB_DENIED_TOOLS` | `--deny-tools` | 無 | 停用這些工具，優先於允許清單 |
| `MCPYLIB_TRANSPORT` | `--transport` | `stdio` | `stdio` 或 `http` |
| `MCPYLIB_HTTP_HOST` | `--host` | `127.0.0.1` | HTTP 綁定位址 |
| `MCPYLIB_HTTP_PORT` | `--port` | `8000` | HTTP 連接埠，端點為 `/mcp` |
| `MCPYLIB_LOG_LEVEL` | `--log-level` | `INFO` | 日誌等級，日誌輸出到 stderr |

## 安全須知

- **方塊上限。**`MCPYLIB_MAX_BLOCKS` 限制每次方塊操作的範圍。超過上限的請求不會送到伺服器，代理會收到「請分批處理」的提示。
- **唯讀模式。**`--read-only` 只提供 21 個唯讀工具，客戶端完全看不到會修改世界的工具。
- **`run_command`。**這個工具能執行任何主控台指令，不受上述限制。如果不需要，請用 `MCPYLIB_DENIED_TOOLS=run_command` 停用它。
- **Token。**token 等同伺服器的完整控制權。若外洩，請執行 `/mcpylib token regenerate` 產生新的 token。

完整的工具列表與詳細說明請見[英文說明](README.md)。

## 相關專案

- [MCPyLib](https://github.com/treeleaves30760/MCPyLib)：Python 函式庫與 Spigot/Paper 插件
- [MCPyLib-skills](https://github.com/treeleaves30760/MCPyLib-skills)：教 AI 代理使用 MCPyLib 的 Agent Skills
- [MCPyLib 網站](https://treeleaves30760.github.io/MCPyLib-website/)

## 授權

採用 [MCPyLib 非商業授權](LICENSE)，僅限非商業用途。
