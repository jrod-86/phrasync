import asyncio
import socket

from karaokesesh.server import (
    available_port,
    browser_host,
    install_windows_transport_error_filter,
    port_available,
)


class WindowsConnectionReset(ConnectionResetError):
    winerror = 10054


def test_browser_host_maps_wildcard_addresses():
    assert browser_host("0.0.0.0") == "127.0.0.1"
    assert browser_host("127.0.0.1") == "127.0.0.1"


def test_available_port_skips_an_occupied_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        assert not port_available("127.0.0.1", port)
        assert available_port("127.0.0.1", port) > port


def test_windows_proactor_disconnect_is_filtered_without_hiding_other_errors():
    loop = asyncio.new_event_loop()
    forwarded = []
    loop.set_exception_handler(lambda _loop, context: forwarded.append(context))
    try:
        install_windows_transport_error_filter(loop)
        loop.call_exception_handler({
            "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
            "exception": WindowsConnectionReset(),
        })
        assert forwarded == []

        other_error = {"message": "unrelated callback", "exception": RuntimeError("boom")}
        loop.call_exception_handler(other_error)
        assert forwarded == [other_error]
    finally:
        loop.close()
