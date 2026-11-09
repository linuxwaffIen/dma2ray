from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from dma2ray.ping import (
    PING_TYPE_LABELS,
    PING_TYPES,
    http_ping,
    icmp_ping,
    ping_endpoint,
    tcp_ping,
)


class TestPing(unittest.TestCase):
    def test_ping_constants(self):
        self.assertIn("tcp", PING_TYPES)
        self.assertIn("http", PING_TYPES)
        self.assertIn("icmp", PING_TYPES)
        for pt in PING_TYPES:
            self.assertIn(pt, PING_TYPE_LABELS)

    @patch("socket.getaddrinfo")
    @patch("socket.socket")
    def test_tcp_ping_success(self, mock_socket_cls, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("1.1.1.1", 443))
        ]
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        ms = tcp_ping("1.1.1.1", 443, timeout=1.0)
        self.assertIsNotNone(ms)
        self.assertGreaterEqual(ms, 1)

    @patch("socket.getaddrinfo", side_effect=OSError("DNS error"))
    def test_tcp_ping_dns_failure(self, _):
        self.assertIsNone(tcp_ping("invalid.test", 443, timeout=1.0))

    @patch("subprocess.run")
    def test_icmp_ping_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="64 bytes from 1.1.1.1: icmp_seq=1 ttl=64 time=15.4 ms\n",
        )
        ms = icmp_ping("1.1.1.1", timeout=1.0)
        self.assertEqual(ms, 15)

    @patch("subprocess.run")
    def test_icmp_ping_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        self.assertIsNone(icmp_ping("1.1.1.1", timeout=1.0))

    @patch("socket.create_connection")
    def test_http_ping_success(self, mock_create):
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b"H"
        mock_create.return_value = mock_sock
        ms = http_ping("example.com", 80, use_tls=False, timeout=1.0)
        self.assertIsNotNone(ms)
        self.assertGreaterEqual(ms, 1)

    @patch("socket.create_connection", side_effect=OSError("Connection refused"))
    def test_http_ping_failure(self, _):
        self.assertIsNone(http_ping("example.com", 80, use_tls=False, timeout=1.0))

    @patch("dma2ray.ping.tcp_ping", return_value=42)
    @patch("dma2ray.ping.http_ping", return_value=120)
    @patch("dma2ray.ping.icmp_ping", return_value=15)
    def test_ping_endpoint_dispatch(self, mock_icmp, mock_http, mock_tcp):
        self.assertEqual(ping_endpoint("host", 80, "tcp"), 42)
        mock_tcp.assert_called_once_with("host", 80, timeout=4.0)

        self.assertEqual(ping_endpoint("host", 443, "http", use_tls=True), 120)
        mock_http.assert_called_once_with("host", 443, use_tls=True, timeout=4.0)

        self.assertEqual(ping_endpoint("host", 80, "icmp"), 15)
        mock_icmp.assert_called_once_with("host", timeout=4.0)


if __name__ == "__main__":
    unittest.main()
