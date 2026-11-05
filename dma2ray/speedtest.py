from __future__ import annotations

import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_URL = "https://speed.cloudflare.com/__down?bytes=8000000"
MAX_BYTES = 12 * 1024 * 1024

_SOCKS_ERRORS = {
    1: "общая ошибка SOCKS5",
    2: "правила запрещают соединение",
    3: "сеть недоступна",
    4: "хост недоступен",
    5: "соединение отклонено",
    7: "команда не поддерживается",
    8: "тип адреса не поддерживается",
}


@dataclass(frozen=True)
class SpeedResult:
    """Outcome of a proxy speed/latency probe."""

    latency_ms: int | None = None
    mbps: float | None = None
    bytes_read: int = 0
    error: str | None = None


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    buffer = b""
    while len(buffer) < size:
        chunk = sock.recv(size - len(buffer))
        if not chunk:
            raise OSError("SOCKS5: соединение закрыто прокси")
        buffer += chunk
    return buffer


def _address_block(host: str) -> bytes:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        encoded = host.encode("idna")
        if len(encoded) > 255:
            raise OSError("SOCKS5: слишком длинное имя хоста")
        return b"\x03" + bytes([len(encoded)]) + encoded
    if ip.version == 4:
        return b"\x01" + ip.packed
    return b"\x04" + ip.packed


def socks5_connect(
    proxy_host: str,
    proxy_port: int,
    dest_host: str,
    dest_port: int,
    timeout: float = 10.0,
) -> socket.socket:
    """Open a TCP connection to dest through a SOCKS5 proxy (no auth)."""
    sock = socket.create_connection((proxy_host, proxy_port), timeout)
    sock.settimeout(timeout)
    try:
        sock.sendall(b"\x05\x01\x00")
        if _recv_exact(sock, 2) != b"\x05\x00":
            raise OSError("SOCKS5: прокси отклонил авторизацию")
        request = b"\x05\x01\x00" + _address_block(dest_host) + dest_port.to_bytes(2, "big")
        sock.sendall(request)
        head = _recv_exact(sock, 4)
        if head[1] != 0:
            raise OSError(f"SOCKS5: {_SOCKS_ERRORS.get(head[1], 'ошибка соединения')}")
        if head[3] == 0x01:
            _recv_exact(sock, 4 + 2)
        elif head[3] == 0x03:
            length = _recv_exact(sock, 1)[0]
            _recv_exact(sock, length + 2)
        elif head[3] == 0x04:
            _recv_exact(sock, 16 + 2)
        else:
            raise OSError("SOCKS5: неизвестный тип адреса в ответе")
    except BaseException:
        sock.close()
        raise
    return sock


def speed_test(
    proxy_host: str,
    proxy_port: int,
    url: str = DEFAULT_URL,
    timeout: float = 20.0,
    max_bytes: int = MAX_BYTES,
) -> SpeedResult:
    """Measure handshake latency and download throughput through a SOCKS5 proxy."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return SpeedResult(error=f"Неподдерживаемый URL: {url}")
    secure = parts.scheme == "https"
    port = parts.port or (443 if secure else 80)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query

    started = time.perf_counter()
    try:
        sock = socks5_connect(proxy_host, proxy_port, parts.hostname, port, timeout)
    except (OSError, TimeoutError) as exc:
        return SpeedResult(error=str(exc))
    latency_ms = int(round((time.perf_counter() - started) * 1000))

    try:
        if secure:
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=parts.hostname)
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parts.hostname}\r\n"
            "User-Agent: dma2ray/0.2\r\n"
            "Accept: */*\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))

        headers = b""
        while b"\r\n\r\n" not in headers:
            chunk = sock.recv(4096)
            if not chunk:
                return SpeedResult(latency_ms=latency_ms, error="Сервер не вернул заголовки")
            headers += chunk
            if len(headers) > 64 * 1024:
                return SpeedResult(latency_ms=latency_ms, error="Слишком большие заголовки")
        status_line = headers.split(b"\r\n", 1)[0]
        try:
            status = int(status_line.split(b" ")[1])
        except (IndexError, ValueError):
            return SpeedResult(latency_ms=latency_ms, error="Некорректный HTTP-ответ")
        if status >= 400:
            return SpeedResult(latency_ms=latency_ms, error=f"HTTP {status}")

        body = headers.split(b"\r\n\r\n", 1)[1]
        read = len(body)
        download_started = time.perf_counter()
        while read < max_bytes:
            sock.settimeout(timeout)
            try:
                chunk = sock.recv(64 * 1024)
            except (socket.timeout, TimeoutError):
                break
            if not chunk:
                break
            read += len(chunk)
        elapsed = time.perf_counter() - download_started
    except (OSError, ssl.SSLError, TimeoutError) as exc:
        return SpeedResult(latency_ms=latency_ms, error=str(exc))
    finally:
        try:
            sock.close()
        except OSError:
            pass

    if elapsed <= 0 or read <= 0:
        return SpeedResult(
            latency_ms=latency_ms, bytes_read=read, error="Не удалось измерить скорость"
        )
    mbps = round((read * 8) / elapsed / 1_000_000, 1)
    return SpeedResult(latency_ms=latency_ms, mbps=mbps, bytes_read=read)
