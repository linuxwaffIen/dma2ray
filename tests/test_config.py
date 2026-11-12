from __future__ import annotations

import unittest

from dma2ray.config import (
    PRIVATE_NETWORKS,
    TUN_GATEWAY,
    TUN_GATEWAY_V6,
    build_config,
)
from dma2ray.vless import parse_hysteria2, parse_shadowsocks, parse_trojan, parse_vless

UUID = "11111111-2222-3333-4444-555555555555"


def make_profile(transport: str = "ws") -> object:
    return parse_vless(
        f"vless://{UUID}@127.0.0.1:443?encryption=none&security=tls"
        f"&sni=example.com&type={transport}&path=%2Fws&host=example.com"
    )


class BuildConfigTests(unittest.TestCase):
    def test_socks_mode(self) -> None:
        config = build_config(make_profile(), tun=False, socks_port=11080, http_port=11081)
        self.assertNotIn("dns", config)
        tags = [inbound["tag"] for inbound in config["inbounds"]]
        self.assertEqual(tags, ["socks-in", "http-in"])
        socks = config["inbounds"][0]
        http = config["inbounds"][1]
        self.assertEqual(socks["port"], 11080)
        self.assertEqual(http["port"], 11081)
        self.assertEqual(socks["listen"], "127.0.0.1")
        self.assertTrue(socks["settings"]["udp"])
        self.assertEqual(
            [outbound["tag"] for outbound in config["outbounds"]],
            ["proxy", "direct", "block"],
        )
        self.assertEqual(config["routing"]["rules"], [])

    def test_tun_mode(self) -> None:
        config = build_config(
            make_profile(), tun=True, socks_port=11080, http_port=11081, enable_ipv6=True
        )
        tags = [inbound["tag"] for inbound in config["inbounds"]]
        self.assertEqual(tags, ["tun-in", "socks-in", "http-in"])
        tun = config["inbounds"][0]
        self.assertEqual(tun["protocol"], "tun")
        self.assertEqual(tun["settings"]["gateway"], [TUN_GATEWAY, TUN_GATEWAY_V6])
        self.assertEqual(
            tun["settings"]["autoSystemRoutingTable"], ["0.0.0.0/0", "::/0"]
        )
        self.assertEqual(tun["settings"]["autoOutboundsInterface"], "auto")
        self.assertNotIn("autoSystemDnsToGateway", tun["settings"])

        self.assertIn("dns", config)
        self.assertEqual(config["dns"]["tag"], "dns-in")
        self.assertTrue(
            all(server.startswith("https://") for server in config["dns"]["servers"])
        )
        dns_out = [out for out in config["outbounds"] if out["tag"] == "dns-out"]
        self.assertEqual(len(dns_out), 1)
        self.assertEqual(dns_out[0]["protocol"], "dns")

    def test_tun_mode_ipv4_only(self) -> None:
        config = build_config(
            make_profile(), tun=True, socks_port=11080, http_port=11081, enable_ipv6=False
        )
        tun = config["inbounds"][0]
        self.assertEqual(tun["settings"]["gateway"], [TUN_GATEWAY])
        self.assertEqual(tun["settings"]["autoSystemRoutingTable"], ["0.0.0.0/0"])

        rules = config["routing"]["rules"]
        self.assertTrue(rules)
        private_rules = [rule for rule in rules if rule.get("ip") == PRIVATE_NETWORKS]
        self.assertEqual(len(private_rules), 1)
        self.assertEqual(private_rules[0]["outboundTag"], "direct")
        self.assertNotIn("::/0", tun["settings"]["autoSystemRoutingTable"])

    def test_ports_must_differ(self) -> None:
        with self.assertRaises(ValueError):
            build_config(make_profile(), tun=False, socks_port=1080, http_port=1080)

    def test_port_range(self) -> None:
        with self.assertRaises(ValueError):
            build_config(make_profile(), tun=False, socks_port=0, http_port=1080)
        with self.assertRaises(ValueError):
            build_config(make_profile(), tun=False, socks_port=1080, http_port=70000)

    def test_log_level_is_copied(self) -> None:
        config = build_config(make_profile(), tun=False, log_level="debug")
        self.assertEqual(config["log"]["loglevel"], "debug")

    def test_trojan_outbound_is_generated(self) -> None:
        profile = parse_trojan("trojan://passw0rd@example.com:443?path=/&security=tls")
        config = build_config(profile, tun=False)
        proxy = config["outbounds"][0]
        self.assertEqual(proxy["tag"], "proxy")
        self.assertEqual(proxy["protocol"], "trojan")
        self.assertEqual(proxy["settings"]["server"], "example.com")
        self.assertEqual(proxy["settings"]["server_port"], 443)

    def test_shadowsocks_outbound_is_generated(self) -> None:
        profile = parse_shadowsocks("ss://aes-128-gcm:passw0rd@example.com:443")
        config = build_config(profile, tun=False)
        proxy = config["outbounds"][0]
        self.assertEqual(proxy["tag"], "proxy")
        self.assertEqual(proxy["protocol"], "shadowsocks")
        self.assertEqual(proxy["settings"]["server"], "example.com")
        self.assertEqual(proxy["settings"]["server_port"], 443)

    def test_shadowsocks_2022_plain_userinfo(self) -> None:
        profile = parse_shadowsocks(
            "ss://2022-blake3-aes-256-gcm%3AaGVsbG8lMjB3b3JsZA%3D%3D"
            "@example.com:8388#SS2022"
        )
        self.assertEqual(profile.security, "2022-blake3-aes-256-gcm")
        self.assertEqual(profile.uuid, "aGVsbG8lMjB3b3JsZA==")
        self.assertEqual(profile.name, "SS2022")

    def test_shadowsocks_sip002_base64_userinfo(self) -> None:
        import base64

        userinfo = base64.urlsafe_b64encode(
            b"chacha20-ietf-poly1305:secret:pass"
        ).decode().rstrip("=")
        profile = parse_shadowsocks(f"ss://{userinfo}@example.com:443#node")
        self.assertEqual(profile.security, "chacha20-ietf-poly1305")
        self.assertEqual(profile.uuid, "secret:pass")
        self.assertEqual(profile.name, "node")

    def test_shadowsocks_legacy_base64_uri(self) -> None:
        import base64

        payload = base64.b64encode(
            b"aes-256-gcm:passw0rd@example.com:443#legacy"
        ).decode()
        profile = parse_shadowsocks(f"ss://{payload}")
        self.assertEqual(profile.security, "aes-256-gcm")
        self.assertEqual(profile.uuid, "passw0rd")
        self.assertEqual(profile.address, "example.com")
        self.assertEqual(profile.port, 443)
        self.assertEqual(profile.name, "legacy")

    def test_shadowsocks_plugin_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_shadowsocks(
                "ss://aes-128-gcm:passw0rd@example.com:443"
                "?plugin=obfs-local%3Bobfs%3Dhttp"
            )

    def test_hysteria2_outbound_is_generated(self) -> None:
        profile = parse_hysteria2("hysteria2://host.com:443?p=passw0rd")
        config = build_config(profile, tun=False)
        proxy = config["outbounds"][0]
        self.assertEqual(proxy["tag"], "proxy")
        self.assertEqual(proxy["protocol"], "hysteria")
        self.assertEqual(proxy["settings"]["server"], "host.com")
        self.assertEqual(proxy["settings"]["port"], 443)


if __name__ == "__main__":
    unittest.main()
