"""Keep the READMEs in step with the code."""

from pathlib import Path

import pytest

from mcpylib_mcp.bridge import MinecraftBridge
from mcpylib_mcp.config import ENV_VARS, Settings
from mcpylib_mcp.server import build_registry

ROOT = Path(__file__).resolve().parent.parent


def tool_names() -> list[str]:
    settings = Settings(token="unused")
    return [spec.name for spec in build_registry(settings, MinecraftBridge.from_settings(settings)).specs]


def test_readme_documents_every_tool():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert [name for name in tool_names() if f"`{name}`" not in readme] == []


@pytest.mark.parametrize("filename", ["README.md", "README.zh-TW.md"])
def test_readme_documents_every_environment_variable(filename):
    text = (ROOT / filename).read_text(encoding="utf-8")

    assert [env for env in ENV_VARS.values() if f"`{env}`" not in text] == []
