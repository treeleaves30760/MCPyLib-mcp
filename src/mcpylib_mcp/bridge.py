"""Thread-safe access to a single MCPyLib client.

MCPyLib keeps one persistent TCP connection that is not safe to share between threads, while
the MCP SDK runs synchronous tools on worker threads (and HTTP clients can call tools
concurrently). Every call therefore goes through one lock. Failures are translated into
:class:`~mcpylib_mcp.errors.MinecraftError` with actionable messages that never include the token.
"""

from __future__ import annotations

import logging
import threading
import traceback
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import mcpylib

from .errors import MinecraftError

if TYPE_CHECKING:
    from .config import Settings

logger = logging.getLogger(__name__)


class MinecraftBridge:
    """Serializes calls to one :class:`mcpylib.MCPyLib` client and translates its errors."""

    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        timeout: float = 30.0,
        *,
        client_factory: Callable[..., Any] = mcpylib.MCPyLib,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        # Creating the client does not connect; MCPyLib connects lazily on the first command.
        self._client = client_factory(ip=host, port=port, token=token, timeout=timeout)
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> MinecraftBridge:
        return cls(settings.host, settings.port, settings.token, settings.timeout)

    @property
    def target(self) -> str:
        """``host:port`` of the MCPyLib plugin."""
        return f"{self._host}:{self._port}"

    def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke ``MCPyLib.<method>(*args, **kwargs)`` and return the plugin's ``data``."""
        with self._lock:
            logger.debug("MCPyLib call: %s", method)
            function = getattr(self._client, method)
            try:
                try:
                    return function(*args, **kwargs)
                except AttributeError as exc:
                    if not _raised_by_stale_socket_check(exc):
                        raise
                    # mcpylib (<= 1.2.0) raises AttributeError from _ensure_connected() when the
                    # plugin closed the previous connection (e.g. after a server restart). That
                    # happens before anything is sent and leaves the client disconnected, so one
                    # more attempt simply reconnects and cannot run the command twice.
                    logger.info("The MCPyLib plugin closed the connection; reconnecting")
                    return function(*args, **kwargs)
            except mcpylib.AuthenticationError as exc:
                raise MinecraftError(
                    f"Authentication failed: the MCPyLib plugin at {self.target} rejected the token "
                    f"({exc}). Set MCPYLIB_TOKEN to the value printed by '/mcpylib token' on the "
                    "Minecraft server."
                ) from exc
            except mcpylib.CommandError as exc:
                raise MinecraftError(f"The Minecraft server rejected the request: {exc}") from exc
            except mcpylib.ConnectionError as exc:
                self._reset()
                raise MinecraftError(
                    f"Cannot reach the MCPyLib plugin at {self.target}: {exc}. Check that the Minecraft "
                    "server is running with the MCPyLib plugin enabled and that MCPYLIB_HOST and "
                    "MCPYLIB_PORT point at the plugin's port."
                ) from exc
            except TimeoutError as exc:
                self._reset()
                raise MinecraftError(
                    f"Timed out after {self._timeout:g}s waiting for the Minecraft server at {self.target}. "
                    "The server may be lagging or the request may be too large. The change may still "
                    "have been applied, so check before retrying; raise MCPYLIB_TIMEOUT for slow "
                    "operations."
                ) from exc
            except OSError as exc:
                self._reset()
                raise MinecraftError(f"Lost the connection to the MCPyLib plugin at {self.target}: {exc}") from exc
            except ValueError as exc:  # json.JSONDecodeError, UnicodeDecodeError
                self._reset()
                raise MinecraftError(
                    f"{self.target} sent a reply that is not a valid MCPyLib response. Is MCPYLIB_PORT "
                    "the MCPyLib plugin's port (65535 by default)?"
                ) from exc
            except mcpylib.MCPyLibError as exc:
                raise MinecraftError(f"MCPyLib error: {exc}") from exc

    def close(self) -> None:
        """Close the connection; the next call reconnects."""
        with self._lock:
            self._reset()

    def _reset(self) -> None:
        try:
            self._client.close()
        except Exception:  # pragma: no cover - closing a broken socket must never mask the real error
            logger.debug("Ignoring error while closing the MCPyLib connection", exc_info=True)


def _raised_by_stale_socket_check(exc: BaseException) -> bool:
    """True if ``exc`` came out of MCPyLib's connection liveness check (``_ensure_connected``)."""
    return any(frame.f_code.co_name == "_ensure_connected" for frame, _ in traceback.walk_tb(exc.__traceback__))
