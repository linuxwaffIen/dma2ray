from __future__ import annotations

import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dma2ray.speedtest import SpeedResult, _address_block, socks5_connect, speed_test


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    buffer = b""
    while len(buffer) < size:
        chunk = sock.recv(size - len(buffer))
        if not chunk:
            raise OSError("closed")
        buffer += chunk
    return buffer


def _pump(left: socket.socket, right: socket.socket) -> None:
    try:
        while True:
            data = left.recv(65536)
            if not data:
                break
            right.sendall(data)
    except OSError:
        pass
    finally:
        try:
            right.shutdown(socket.SHUT_WR)
        except OSError:
            pass


class Socks5Server:
    """Minimal localhost SOCKS5 proxy (no auth) for tests."""

    def __init__(self) -> None:
        self._listener = socket.socket()
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(8)
        self.port = self._listener.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        try:
            self._listener.close()
        except OSError:
            pass

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._listener.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        upstream: socket.socket | None = None
        try:
            conn.settimeout(10)
            head = _recv_exact(conn, 2)
            if head != b"\x05\x01":
                return
            _recv_exact(conn, 1)  # one method offered: no-auth
            conn.sendall(b"\x05\x00")
            request = _recv_exact(conn, 4)
            if request[:3] != b"\x05\x01\x00":
                return
            atyp = request[3]
            if atyp == 0x01:
                host = socket.inet_ntoa(_recv_exact(conn, 4))
            elif atyp == 0x03:
                length = _recv_exact(conn, 1)[0]
                host = _recv_exact(conn, length).decode("idna")
            elif atyp == 0x04:
                host = socket.inet_ntop(socket.AF_INET6, _recv_exact(conn, 16))
            else:
                return
            port = int.from_bytes(_recv_exact(conn, 2), "big")
            upstream = socket.create_connection((host, port), 10)
            conn.sendall(b"\x05\x00\x00\x01" + b"\x00" * 6)
            threading.Thread(target=_pump, args=(upstream, conn), daemon=True).start()
            _pump(conn, upstream)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass
            if upstream is not None:
                try:
                    upstream.close()
                except OSError:
                    pass


class _PayloadHandler(BaseHTTPRequestHandler):
    payload = b"dma2ray-speed-test" * 100_000  # ~2 MB

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        try:
            self.wfile.write(self.payload)
        except OSError:
            pass

    def log_message(self, *_args) -> None:
        pass


class AddressBlockTests(unittest.TestCase):
    def test_hostname(self) -> None:
        block = _address_block("example.com")
        self.assertEqual(block[0], 0x03)
        self.assertEqual(block[1], len(b"example.com"))
        self.assertEqual(block[2:], b"example.com")

    def test_ipv4(self) -> None:
        self.assertEqual(_address_block("127.0.0.1"), b"\x01" + bytes([127, 0, 0, 1]))

    def test_ipv6(self) -> None:
        block = _address_block("::1")
        self.assertEqual(block[0], 0x04)
        self.assertEqual(len(block), 1 + 16)


class Socks5ConnectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proxy = Socks5Server()
        self.addCleanup(self.proxy.close)

    def test_roundtrip_through_proxy(self) -> None:
        target = socket.socket()
        target.bind(("127.0.0.1", 0))
        target.listen(1)
        port = target.getsockname()[1]

        def serve() -> None:
            conn, _ = target.accept()
            try:
                conn.sendall(b"hello")
                conn.recv(16)
            finally:
                conn.close()
                target.close()

        threading.Thread(target=serve, daemon=True).start()
        sock = socks5_connect("127.0.0.1", self.proxy.port, "127.0.0.1", port, timeout=5)
        try:
            self.assertEqual(sock.recv(5), b"hello")
            sock.sendall(b"ping")
        finally:
            sock.close()

    def test_connection_refused_reports_error(self) -> None:
        closed = socket.socket()
        closed.bind(("127.0.0.1", 0))
        closed_port = closed.getsockname()[1]
        closed.close()
        with self.assertRaises(OSError):
            socks5_connect("127.0.0.1", self.proxy.port, "127.0.0.1", closed_port, timeout=5)


class SpeedTestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.proxy = Socks5Server()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _PayloadHandler)
        cls.http_port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.proxy.close()
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_download_through_proxy(self) -> None:
        url = f"http://127.0.0.1:{self.http_port}/down"
        result = speed_test(
            "127.0.0.1",
            self.proxy.port,
            url=url,
            timeout=10.0,
            max_bytes=512 * 1024,
        )
        self.assertIsNone(result.error, result.error)
        self.assertIsNotNone(result.latency_ms)
        self.assertGreaterEqual(result.bytes_read, 100_000)
        self.assertIsNotNone(result.mbps)
        self.assertGreater(result.mbps, 0)

    def test_unsupported_scheme(self) -> None:
        result = speed_test("127.0.0.1", self.proxy.port, url="ftp://example.com/file")
        self.assertIsNone(result.mbps)
        self.assertIn("Неподдерживаемый", result.error or "")

    def test_proxy_down_reports_error(self) -> None:
        result = speed_test("127.0.0.1", 1, url="http://example.com/", timeout=2.0)
        self.assertIsNotNone(result.error)
        self.assertIsNone(result.mbps)

    def test_speed_result_defaults(self) -> None:
        result = SpeedResult()
        self.assertIsNone(result.latency_ms)
        self.assertIsNone(result.mbps)
        self.assertIsNone(result.error)


if __name__ == "__main__":
    unittest.main()
