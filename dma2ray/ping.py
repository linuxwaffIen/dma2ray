from __future__ import annotations

import platform
import re
import socket
import ssl
import subprocess
import time

PING_TYPES = ("tcp", "http", "icmp")
PING_TYPE_LABELS = {
    "tcp": "TCP (рукопожатие)",
    "http": "HTTP / TLS (запрос к серверу)",
    "icmp": "ICMP (системный пинг)",
}


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
            return int(round(elapsed))
        except OSError:
            continue
        finally:
            sock.close()
    return None


def icmp_ping(host: str, timeout: float = 4.0) -> int | None:
    """System ICMP ping. Returns milliseconds or None."""
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
    elif system == "darwin":
        cmd = ["ping", "-c", "1", "-W", str(int(timeout * 1000)), host]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, int(timeout))), host]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout + 1.0,
        )
        if proc.returncode != 0:
            return None
        match = re.search(r"time[=<](\d+\.?\d*)\s*ms", proc.stdout, re.IGNORECASE)
        if match:
            return int(round(float(match.group(1))))
        match_rtt = re.search(r"=\s*[\d\.]+/([\d\.]+)/", proc.stdout)
        if match_rtt:
            return int(round(float(match_rtt.group(1))))
        return None
    except (OSError, subprocess.TimeoutExpired):
        return None


def http_ping(host: str, port: int, use_tls: bool = False, timeout: float = 4.0) -> int | None:
    """Measure HTTP/HTTPS response latency to endpoint. Returns milliseconds or None."""
    try:
        started = time.perf_counter()
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(timeout)
        if use_tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(sock, server_hostname=host)
        sock.sendall(f"HEAD / HTTP/1.1\r\nHost: {host}\r\nUser-Agent: dma2ray\r\nConnection: close\r\n\r\n".encode())
        if not sock.recv(1):
            sock.close()
            return None
        elapsed = (time.perf_counter() - started) * 1000
        sock.close()
        return int(round(elapsed))
    except (OSError, ssl.SSLError):
        return None


def ping_endpoint(
    host: str,
    port: int,
    ping_type: str = "tcp",
    timeout: float = 4.0,
    use_tls: bool = False,
) -> int | None:
    """Measure endpoint latency using the configured ping method."""
    if ping_type == "icmp":
        return icmp_ping(host, timeout=timeout)
    if ping_type == "http":
        return http_ping(host, port, use_tls=use_tls, timeout=timeout)
    return tcp_ping(host, port, timeout=timeout)
