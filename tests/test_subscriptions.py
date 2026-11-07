from __future__ import annotations

import base64
import json
import unittest

from dma2ray.subscriptions import _decode_payload, parse_subscription
from dma2ray.vless import (
    VlessError,
    parse_hysteria2,
    parse_shadowsocks,
    parse_trojan,
    parse_vless,
    parse_vmess,
)

UUID = "11111111-2222-3333-4444-555555555555"
URI_1 = f"vless://{UUID}@example.com:443?type=ws&security=tls#One"
URI_2 = f"vless://{UUID}@example.net:443?type=grpc&security=tls#Two"


class SubscriptionTests(unittest.TestCase):
    def test_plain_text(self) -> None:
        result = parse_subscription(f"# comment\n{URI_1}\n\n{URI_2}\n")
        self.assertEqual(result.raw_count, 2)
        self.assertEqual(result.entries, [("One", URI_1), ("Two", URI_2)])
        self.assertEqual(result.unsupported, 0)
        self.assertEqual(result.invalid, 0)

    def test_base64_payload(self) -> None:
        payload = f"{URI_1}\n{URI_2}\n".encode()
        encoded = base64.b64encode(payload).decode()
        result = parse_subscription(encoded)
        self.assertEqual([name for name, _uri in result.entries], ["One", "Two"])

    def test_url_safe_base64_without_padding(self) -> None:
        payload = f"{URI_1}\n".encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        result = parse_subscription(encoded)
        self.assertEqual(result.entries, [("One", URI_1)])

    def test_duplicates_are_skipped(self) -> None:
        result = parse_subscription(f"{URI_1}\n{URI_1}\n")
        self.assertEqual(result.raw_count, 2)
        self.assertEqual(len(result.entries), 1)

    def test_unsupported_and_invalid_are_counted(self) -> None:
        text = "\n".join(
            [
                URI_1,
                "vmess://abc",
                "trojan://abc",
                "vless://broken",
                "not a link",
            ]
        )
        result = parse_subscription(text)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.unsupported, 0)
        self.assertEqual(result.invalid, 3)
        self.assertEqual(result.raw_count, 4)

    def test_comments_are_ignored(self) -> None:
        result = parse_subscription(f"# {URI_1}\n// {URI_2}\n")
        self.assertEqual(result.entries, [])

    def test_decode_payload_leaves_plain_text(self) -> None:
        self.assertEqual(_decode_payload(URI_1), URI_1)
        self.assertEqual(_decode_payload(""), "")
        self.assertEqual(_decode_payload("not base64 at all"), "not base64 at all")

    def test_empty_subscription(self) -> None:
        result = parse_subscription("")
        self.assertEqual(result.entries, [])
        self.assertEqual(result.total, 0)

    def test_parse_trojan(self) -> None:
        uri = "trojan://passw0rd@example.com:443?path=/&security=tls"
        profile = parse_trojan(uri)
        self.assertEqual(profile.protocol, "trojan")
        self.assertEqual(profile.uuid, "passw0rd")
        self.assertEqual(profile.address, "example.com")
        self.assertEqual(profile.port, 443)

    def test_parse_shadowsocks(self) -> None:
        uri = "ss://aes-128-gcm:passw0rd@example.com:443"
        profile = parse_shadowsocks(uri)
        self.assertEqual(profile.protocol, "shadowsocks")
        self.assertEqual(profile.security, "aes-128-gcm")
        self.assertEqual(profile.uuid, "passw0rd")
        self.assertEqual(profile.address, "example.com")
        self.assertEqual(profile.port, 443)

    def test_parse_vmess(self) -> None:
        import base64 as b64

        data = {"add": "example.com", "port": 443, "id": "11111111-2222-3333-4444-555555555555", "ps": "MyVMess"}
        payload = b64.b64encode(json.dumps(data).encode()).decode()
        uri = f"vmess://{payload}"
        profile = parse_vmess(uri)
        self.assertEqual(profile.protocol, "vless")
        self.assertEqual(profile.address, "example.com")
        self.assertEqual(profile.port, 443)

    def test_parse_hysteria2(self) -> None:
        uri = "hysteria2://host.com:443?p=passw0rd"
        profile = parse_hysteria2(uri)
        self.assertEqual(profile.protocol, "hysteria")
        self.assertEqual(profile.uuid, "passw0rd")
        self.assertEqual(profile.address, "host.com")
        self.assertEqual(profile.port, 443)


if __name__ == "__main__":
    unittest.main()
