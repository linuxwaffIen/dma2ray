from __future__ import annotations

import unittest

from dma2ray.vless import VlessError, parse_vless

UUID = "11111111-2222-3333-4444-555555555555"


class ParseVlessTests(unittest.TestCase):
    def test_ws_tls_profile(self) -> None:
        uri = (
            f"vless://{UUID}@example.com:443?encryption=none&security=tls"
            "&sni=cdn.example.com&type=ws&host=cdn.example.com&path=%2Fws"
            "&alpn=h2%2Chttp%2F1.1&fp=chrome#My%20Server"
        )
        profile = parse_vless(uri)
        self.assertEqual(profile.uuid, UUID)
        self.assertEqual(profile.address, "example.com")
        self.assertEqual(profile.port, 443)
        self.assertEqual(profile.name, "My Server")
        self.assertEqual(profile.security, "tls")
        self.assertEqual(profile.network, "ws")
        self.assertEqual(profile.sni, "cdn.example.com")
        self.assertEqual(profile.host_header, "cdn.example.com")
        self.assertEqual(profile.path, "/ws")
        self.assertEqual(profile.alpn, ["h2", "http/1.1"])
        stream = profile.to_xray_stream()
        self.assertEqual(stream["network"], "ws")
        self.assertEqual(stream["security"], "tls")
        self.assertEqual(stream["wsSettings"]["host"], "cdn.example.com")
        self.assertEqual(stream["tlsSettings"]["serverName"], "cdn.example.com")
        self.assertEqual(stream["tlsSettings"]["fingerprint"], "chrome")

    def test_reality_profile(self) -> None:
        uri = (
            f"vless://{UUID}@example.com:443?security=reality&sni=www.microsoft.com"
            "&fp=chrome&pbk=public-key&sid=0123&spx=%2F&type=tcp"
            "&flow=xtls-rprx-vision#Reality"
        )
        profile = parse_vless(uri)
        self.assertEqual(profile.security, "reality")
        self.assertEqual(profile.public_key, "public-key")
        self.assertEqual(profile.short_id, "0123")
        self.assertEqual(profile.flow, "xtls-rprx-vision")
        stream = profile.to_xray_stream()
        self.assertEqual(stream["realitySettings"]["publicKey"], "public-key")
        self.assertEqual(stream["realitySettings"]["shortId"], "0123")
        outbound = profile.to_xray_outbound()
        self.assertEqual(
            outbound["settings"]["vnext"][0]["users"][0]["flow"],
            "xtls-rprx-vision",
        )

    def test_transport_variants(self) -> None:
        cases = {
            "grpc": f"vless://{UUID}@example.com:443?type=grpc&serviceName=svc",
            "httpupgrade": (
                f"vless://{UUID}@example.com:443?type=httpupgrade"
                "&host=example.com&path=%2Fup"
            ),
            "xhttp": (
                f"vless://{UUID}@example.com:443?type=xhttp"
                "&host=example.com&path=%2Fx&mode=packet-up"
            ),
            "kcp": (
                f"vless://{UUID}@example.com:443?type=kcp"
                "&headerType=wechat-video&seed=abc"
            ),
            "tcp-http": (
                f"vless://{UUID}@example.com:443?type=tcp"
                "&headerType=http&host=a.example.com,b.example.com&path=%2Fh"
            ),
        }
        grpc = parse_vless(cases["grpc"])
        self.assertEqual(grpc.to_xray_stream()["grpcSettings"]["serviceName"], "svc")

        upgrade = parse_vless(cases["httpupgrade"])
        self.assertEqual(
            upgrade.to_xray_stream()["httpupgradeSettings"],
            {"path": "/up", "host": "example.com"},
        )

        xhttp = parse_vless(cases["xhttp"])
        self.assertEqual(
            xhttp.to_xray_stream()["xhttpSettings"],
            {"path": "/x", "host": "example.com", "mode": "packet-up"},
        )

        kcp = parse_vless(cases["kcp"])
        self.assertEqual(
            kcp.to_xray_stream()["kcpSettings"],
            {"header": {"type": "wechat-video"}, "seed": "abc"},
        )

        tcp_http = parse_vless(cases["tcp-http"])
        header = tcp_http.to_xray_stream()["tcpSettings"]["header"]
        self.assertEqual(header["type"], "http")
        self.assertEqual(
            header["request"]["headers"]["Host"],
            ["a.example.com", "b.example.com"],
        )

    def test_raw_is_mapped_to_tcp(self) -> None:
        profile = parse_vless(f"vless://{UUID}@example.com:443?type=raw")
        self.assertEqual(profile.network, "raw")
        self.assertEqual(profile.to_xray_stream()["network"], "tcp")

    def test_ipv6_address(self) -> None:
        profile = parse_vless(f"vless://{UUID}@[2001:db8::1]:8443?type=tcp")
        self.assertEqual(profile.address, "2001:db8::1")
        self.assertEqual(profile.endpoint, "[2001:db8::1]:8443")
        self.assertEqual(
            profile.to_xray_outbound()["settings"]["vnext"][0]["address"],
            "2001:db8::1",
        )

    def test_address_override(self) -> None:
        profile = parse_vless(f"vless://{UUID}@example.com:443?type=tcp")
        outbound = profile.to_xray_outbound("203.0.113.7")
        self.assertEqual(
            outbound["settings"]["vnext"][0]["address"], "203.0.113.7"
        )

    def test_name_fallback(self) -> None:
        profile = parse_vless(f"vless://{UUID}@example.com:443")
        self.assertEqual(profile.name, "example.com:443")
        self.assertEqual(profile.port, 443)

    def test_default_port(self) -> None:
        profile = parse_vless(f"vless://{UUID}@example.com")
        self.assertEqual(profile.port, 443)

    def test_invalid_links(self) -> None:
        invalid = [
            "",
            "http://example.com",
            f"vless://@example.com:443",
            f"vless://{UUID}@:443",
            f"vless://{UUID}@example.com:0",
            f"vless://{UUID}@example.com:70000",
            f"vless://{UUID}@example.com:notaport",
            f"vless://{UUID}@[2001:db8::1:443",
            f"vless://{UUID}@example.com:443?type=wireguard",
            f"vless://{UUID}@example.com:443?security=reality&type=tcp",
        ]
        for uri in invalid:
            with self.subTest(uri=uri):
                with self.assertRaises(VlessError):
                    parse_vless(uri)

    def test_removed_transports(self) -> None:
        for transport in ("http", "h2", "http2", "quic"):
            with self.subTest(transport=transport):
                with self.assertRaises(VlessError) as context:
                    parse_vless(
                        f"vless://{UUID}@example.com:443?type={transport}"
                    )
                self.assertIn("не поддерживается ядром mihomo", str(context.exception))

    def test_splithttp_alias(self) -> None:
        profile = parse_vless(f"vless://{UUID}@example.com:443?type=splithttp")
        self.assertEqual(profile.network, "xhttp")


if __name__ == "__main__":
    unittest.main()
