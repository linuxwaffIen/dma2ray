from __future__ import annotations

import socket
import time


def tcp_ping(host: str, port: int, timeout: float = 4.0) -> int | None:
    """Measure a TCP handshake to the endpoint. Returns milliseconds or None."""
    deadline = time.monotonic() + max(0.5, timeout)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return None
    for family, sock_type, proto, _canon, sockaddr in infos[:4]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        sock = socket.socket(family, sock_type, proto)
        try:
            sock.settimeout(remaining)
            started = time.perf_counter()
            sock.connect(sockaddr)
            elapsed = (time.perf_counter() - started) * 1000
            return max(1, int(round(elapsed)))
        except OSError:
            continue
        finally:
            sock.close()
    return None
