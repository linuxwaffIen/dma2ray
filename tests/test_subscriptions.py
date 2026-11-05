from __future__ import annotations

import base64
import unittest

from dma2ray.subscriptions import _decode_payload, parse_subscription

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
        self.assertEqual(result.unsupported, 2)
        self.assertEqual(result.invalid, 1)
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


if __name__ == "__main__":
    unittest.main()
