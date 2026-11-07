from __future__ import annotations

import ipaddress
from typing import Any

from .vless import VlessProfile

TUN_NAME = "tun0"
TUN_GATEWAY = "172.19.0.1"
TUN_GATEWAY_V6 = "fdfe:dcba:9876::1"
TUN_MTU = 1500
DNS_TAG = "dns-in"

PRIVATE_NETWORKS = [
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "100.64.0.0/10",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
    "ff00::/8",
]

PUBLIC_DNS = [
    "https://1.1.1.1/dns-query",
    "https://8.8.8.8/dns-query",
]


def _private_rule() -> dict[str, Any]:
    return {
        "type": "field",
        "ip": PRIVATE_NETWORKS,
        "outboundTag": "direct",
    }


def build_config(
    profile: VlessProfile,
    *,
    tun: bool,
    socks_port: int = 10808,
    http_port: int = 10809,
    log_level: str = "warning",
    address_override: str | None = None,
) -> dict[str, Any]:
    if not 1 <= socks_port <= 65535 or not 1 <= http_port <= 65535:
        raise ValueError("Порты должны быть в диапазоне 1..65535")
    if socks_port == http_port:
        raise ValueError("SOCKS и HTTP порты должны различаться")

    inbounds: list[dict[str, Any]] = []
    if tun:
        inbounds.append(
            {
                "tag": "tun-in",
                "port": 0,
                "protocol": "tun",
                "settings": {
                    "name": TUN_NAME,
                    "desc": "Dma2ray TUN",
                    "mtu": TUN_MTU,
                    "gateway": [TUN_GATEWAY, TUN_GATEWAY_V6],
                    # Xray only assigns this list to the interface on Windows;
                    # on Linux DNS is hijacked through routing below.
                    "dns": ["1.1.1.1", "8.8.8.8"],
                    "autoSystemRoutingTable": ["0.0.0.0/0", "::/0"],
                    "autoOutboundsInterface": "auto",
                },
            }
        )
    inbounds.extend(
        [
            {
                "tag": "socks-in",
                "listen": "127.0.0.1",
                "port": int(socks_port),
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
            },
            {
                "tag": "http-in",
                "listen": "127.0.0.1",
                "port": int(http_port),
                "protocol": "http",
                "settings": {"allowTransparent": False},
            },
        ]
    )

    outbounds: list[dict[str, Any]] = [
        profile.to_xray_outbound(address_override),
        {
            "tag": "direct",
            "protocol": "freedom",
            "settings": {},
        },
        {
            "tag": "block",
            "protocol": "blackhole",
            "settings": {},
        },
    ]
    if tun:
        outbounds.append({"tag": "dns-out", "protocol": "dns"})

    config: dict[str, Any] = {
        "log": {"loglevel": log_level},
        "inbounds": inbounds,
        "outbounds": outbounds,
    }

    if tun:
        config["dns"] = {
            "tag": DNS_TAG,
            "servers": PUBLIC_DNS,
            "queryStrategy": "UseIP",
            "disableCache": False,
            "serveStale": True,
        }
        config["routing"] = {
            "domainStrategy": "AsIs",
            "rules": [
                # DNS requests made by Xray itself (DoH) go through the tunnel.
                {"type": "field", "inboundTag": [DNS_TAG], "outboundTag": "proxy"},
                # Hijack any DNS traffic that arrives through the TUN interface.
                {
                    "type": "field",
                    "inboundTag": ["tun-in"],
                    "port": "53",
                    "outboundTag": "dns-out",
                },
                # Keep LAN/private destinations local.
                _private_rule(),
            ],
        }
    else:
        config["routing"] = {"domainStrategy": "AsIs", "rules": []}

    return config


def is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False
