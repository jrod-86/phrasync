from __future__ import annotations

import asyncio
import json
import socket
from typing import Any
from urllib.request import urlopen

from karaokesesh import APP_NAME


def install_windows_transport_error_filter(
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """Hide the harmless Proactor reset emitted when a browser cancels media I/O.

    Chromium routinely closes an old HTTP range request while seeking or replacing
    a video source. On Windows the Proactor loop can report that normal disconnect
    as WinError 10054 after the response has already been handled successfully.
    """
    event_loop = loop or asyncio.get_running_loop()
    previous_handler = event_loop.get_exception_handler()

    def handle_exception(current_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        error = context.get("exception")
        callback = f"{context.get('message', '')} {context.get('handle', '')}"
        benign_media_disconnect = (
            isinstance(error, ConnectionResetError)
            and getattr(error, "winerror", None) == 10054
            and "_ProactorBasePipeTransport._call_connection_lost" in callback
        )
        if benign_media_disconnect:
            return
        if previous_handler is not None:
            previous_handler(current_loop, context)
        else:
            current_loop.default_exception_handler(context)

    event_loop.set_exception_handler(handle_exception)


def browser_host(host: str) -> str:
    """Return an address a local browser can connect to."""
    return "127.0.0.1" if host in {"0.0.0.0", "::"} else host


def instance_url(host: str, port: int, timeout: float = 0.4) -> str | None:
    """Return the root URL when *port* belongs to a KaraokeSesh instance."""
    root = f"http://{browser_host(host)}:{port}"
    try:
        with urlopen(f"{root}/api/instance", timeout=timeout) as response:
            payload = json.load(response)
        return root if payload.get("app") == APP_NAME else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def port_available(host: str, port: int) -> bool:
    """Check whether a TCP port can be bound without touching its owner."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    bind_host = host
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((bind_host, port))
        except OSError:
            return False
    return True


def available_port(host: str, preferred: int, attempts: int = 100) -> int:
    """Return *preferred* or the next available port in a bounded range."""
    for port in range(preferred, min(preferred + attempts, 65536)):
        if port_available(host, port):
            return port
    raise RuntimeError(f"No available port found from {preferred} to {preferred + attempts - 1}")
