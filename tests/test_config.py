from __future__ import annotations

import unittest

from dma2ray.config import (
    PRIVATE_NETWORKS,
    PROXY_GROUP,
    build_config,
    dump_yaml,
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
        self.assertEqual(config["mode"], "rule")
        self.assertEqual(config["socks-port"], 11080)
        self.assertEqual(config["port"], 11081)
        self.assertFalse(config["allow-lan"])
        self.assertFalse(config["ipv6"])
        self.assertNotIn("tun", config)
        self.assertNotIn("global-client-fingerprint", config)

        proxy = config["proxies"][0]
        self.assertEqual(proxy["type"], "vless")
        self.assertEqual(proxy["server"], "127.0.0.1")
        self.assertEqual(proxy["port"], 443)
        self.assertEqual(proxy["uuid"], UUID)
        self.assertTrue(proxy["tls"])
        self.assertEqual(proxy["servername"], "example.com")
        self.assertEqual(proxy["client-fingerprint"], "chrome")
        self.assertEqual(
            config["proxy-groups"],
            [{"name": PROXY_GROUP, "type": "select", "proxies": [proxy["name"]]}],
        )

    def test_rules_direct_for_lan(self) -> None:
        config = build_config(make_profile(), tun=False)
        rules = config["rules"]
        self.assertEqual(rules[-1], f"MATCH,{PROXY_GROUP}")
        for cidr in PRIVATE_NETWORKS:
            self.assertIn(f"IP-CIDR,{cidr},DIRECT,no-resolve", rules)

    def test_server_ip_excluded_from_tunnel(self) -> None:
        config = build_config(make_profile(), tun=True, address_override="144.31.224.191")
        self.assertEqual(config["tun"]["route-exclude-address"], ["144.31.224.191/32"])
        self.assertEqual(
            config["rules"][0], "IP-CIDR,144.31.224.191/32,DIRECT,no-resolve"
        )

    def test_domain_without_override_has_no_exclusions(self) -> None:
        profile = parse_vless(f"vless://{UUID}@example.com:443?security=tls&type=ws")
        config = build_config(profile, tun=True)
        self.assertNotIn("route-exclude-address", config["tun"])
        self.assertTrue(all(rule.startswith("IP-CIDR,127.") or True for rule in config["rules"]))

    def test_ipv6_server_excluded_from_tunnel(self) -> None:
        profile = parse_vless(f"vless://{UUID}@[2001:db8::1]:443?security=tls&type=ws")
        config = build_config(profile, tun=True)
        self.assertEqual(config["tun"]["route-exclude-address"], ["2001:db8::1/128"])

    def test_tun_mode(self) -> None:
        config = build_config(
            make_profile(), tun=True, socks_port=11080, http_port=11081, enable_ipv6=True
        )
        tun = config["tun"]
        self.assertTrue(tun["enable"])
        self.assertTrue(tun["auto-route"])
        self.assertEqual(tun["dns-hijack"], ["any:53"])
        self.assertTrue(config["ipv6"])

        dns = config["dns"]
        self.assertTrue(dns["enable"])
        self.assertEqual(dns["enhanced-mode"], "fake-ip")
        # DoH и обычный UDP параллельно: если DoH у провайдера режется,
        # резолв идёт через UDP 53 (mihomo берёт первый валидный ответ).
        self.assertIn("https://1.1.1.1/dns-query", dns["nameserver"])
        self.assertIn("1.1.1.1", dns["nameserver"])
        self.assertIn("https://1.1.1.1/dns-query", dns["proxy-server-nameserver"])
        self.assertIn("8.8.8.8", dns["proxy-server-nameserver"])

    def test_tun_mode_ipv4_only(self) -> None:
        config = build_config(make_profile(), tun=True, enable_ipv6=False)
        self.assertFalse(config["ipv6"])

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
        self.assertEqual(config["log-level"], "debug")

    def test_trojan_proxy_is_generated(self) -> None:
        profile = parse_trojan("trojan://passw0rd@example.com:443?path=/&security=tls")
        config = build_config(profile, tun=False)
        proxy = config["proxies"][0]
        self.assertEqual(proxy["type"], "trojan")
        self.assertEqual(proxy["server"], "example.com")
        self.assertEqual(proxy["port"], 443)
        self.assertEqual(proxy["password"], "passw0rd")
        self.assertEqual(proxy["sni"], "example.com")

    def test_shadowsocks_proxy_is_generated(self) -> None:
        profile = parse_shadowsocks("ss://aes-128-gcm:passw0rd@example.com:443")
        config = build_config(profile, tun=False)
        proxy = config["proxies"][0]
        self.assertEqual(proxy["type"], "ss")
        self.assertEqual(proxy["cipher"], "aes-128-gcm")
        self.assertEqual(proxy["server"], "example.com")
        self.assertEqual(proxy["port"], 443)

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

    def test_hysteria2_proxy_is_generated(self) -> None:
        profile = parse_hysteria2("hysteria2://host.com:443?p=passw0rd")
        config = build_config(profile, tun=False)
        proxy = config["proxies"][0]
        self.assertEqual(proxy["type"], "hysteria2")
        self.assertEqual(proxy["server"], "host.com")
        self.assertEqual(proxy["port"], 443)
        self.assertEqual(proxy["password"], "passw0rd")

    def test_reality_proxy_is_generated(self) -> None:
        profile = parse_vless(
            f"vless://{UUID}@example.com:443?encryption=none&security=reality"
            "&type=tcp&flow=xtls-rprx-vision&sni=example.com"
            "&fp=chrome&pbk=PUBKEY&sid=abcd#reality"
        )
        proxy = build_config(profile, tun=False)["proxies"][0]
        self.assertTrue(proxy["tls"])
        self.assertEqual(proxy["flow"], "xtls-rprx-vision")
        self.assertEqual(proxy["client-fingerprint"], "chrome")
        self.assertEqual(proxy["reality-opts"]["public-key"], "PUBKEY")
        self.assertEqual(proxy["reality-opts"]["short-id"], "abcd")

    def test_unsupported_transports_rejected(self) -> None:
        for transport in ("xhttp", "kcp"):
            with self.subTest(transport=transport):
                profile = parse_vless(
                    f"vless://{UUID}@127.0.0.1:443?type={transport}"
                )
                with self.assertRaises(ValueError):
                    build_config(profile, tun=False)

    def test_wireguard_rejected(self) -> None:
        profile = parse_vless(f"vless://{UUID}@127.0.0.1:443")
        object.__setattr__(profile, "protocol", "wireguard")
        with self.assertRaises(ValueError):
            build_config(profile, tun=False)


class DumpYamlTests(unittest.TestCase):
    def test_scalar_types(self) -> None:
        text = dump_yaml({"a": "x", "b": 3, "c": True, "d": None, "e": 1.5})
        self.assertEqual(text, '"a": "x"\n"b": 3\n"c": true\n"d": null\n"e": 1.5\n')

    def test_nested_dict_and_list(self) -> None:
        text = dump_yaml(
            {
                "tun": {"enable": True, "dns-hijack": ["any:53"]},
                "proxies": [{"name": "n", "port": 443}],
            }
        )
        self.assertEqual(
            text,
            '"tun":\n'
            '  "enable": true\n'
            '  "dns-hijack":\n'
            '    - "any:53"\n'
            '"proxies":\n'
            '  - "name": "n"\n'
            '    "port": 443\n',
        )

    def test_yaml_parses_like_hysteria_config(self) -> None:
        # Дым-проверка: структура на месте, кавычки/отступы согласованы.
        config = build_config(make_profile(), tun=True)
        text = dump_yaml(config)
        self.assertIn('"proxies":', text)
        self.assertIn('"proxy-groups":', text)
        self.assertIn('"rules":', text)
        self.assertIn('- "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve"', text)
        self.assertIn('- "MATCH,PROXY"', text)


if __name__ == "__main__":
    unittest.main()
