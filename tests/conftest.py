import socket
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from fake_server import FakeMinecraftServer  # noqa: E402


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def fake() -> Iterator[FakeMinecraftServer]:
    server = FakeMinecraftServer().start()
    yield server
    server.stop()


@pytest.fixture
def free_port() -> int:
    """A local TCP port with nothing listening on it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
