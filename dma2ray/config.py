from __future__ import annotations

import ipaddress
import json
import socket
from pathlib import Path
from typing import Any

from .hysteria import HysteriaProfile
from .vless import VlessProfile

# Имя группы-политики, на которую ссылаются правила маршрутизации.
PROXY_GROUP = "PROXY"

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


def is_ipv6_supported() -> bool:
    try:
        flag = Path("/proc/sys/net/ipv6/conf/all/disable_ipv6")
        if flag.is_file() and flag.read_text().strip() == "1":
            return False
    except OSError:
        pass
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.close()
        return True
    except OSError:
        return False


def _transport_options(profile: VlessProfile, proxy: dict[str, Any]) -> None:
    """Заполнить сетевые опции транспорта (ws/grpc/httpupgrade/tcp)."""
    network = "tcp" if profile.network == "raw" else profile.network
    if network in ("xhttp", "kcp"):
        raise ValueError(
            f"Транспорт {profile.network} не поддерживается ядром mihomo"
        )
    host = [h.strip() for h in profile.host_header.split(",") if h.strip()]
    if network == "ws":
        opts: dict[str, Any] = {"path": profile.path or "/"}
        if host:
            opts["headers"] = {"Host": host[0]}
        proxy["ws-opts"] = opts
        proxy["network"] = "ws"
    elif network == "grpc":
        proxy["grpc-opts"] = {"grpc-service-name": profile.service_name}
        proxy["network"] = "grpc"
    elif network == "httpupgrade":
        opts = {"path": profile.path or "/"}
        if host:
            opts["host"] = host[0]
        proxy["httpupgrade-opts"] = opts
        proxy["network"] = "httpupgrade"
    # tcp: сетевой заголовок не нужен; обфускация tcp-http ядром не поддерживается.
    elif network == "tcp" and profile.header_type == "http":
        raise ValueError("Обфускация tcp-http не поддерживается ядром mihomo")


def _tls_options(profile: VlessProfile, proxy: dict[str, Any]) -> None:
    security = "tls" if profile.security == "xtls" else profile.security
    if security not in ("tls", "reality"):
        return
    proxy["tls"] = True
    if profile.sni or profile.address:
        proxy["servername"] = profile.sni or profile.address
    if profile.allow_insecure:
        proxy["skip-cert-verify"] = True
    if profile.alpn:
        proxy["alpn"] = list(profile.alpn)
    # uTLS-отпечаток браузера: без него ClientHello Go-клиента легко
    # детектируется DPI. Опция global-client-fingerprint удалена из mihomo,
    # поэтому задаём отпечаток прямо в прокси.
    proxy["client-fingerprint"] = profile.fingerprint or "chrome"
    if security == "reality":
        proxy["reality-opts"] = {
            "public-key": profile.public_key,
            "short-id": profile.short_id,
        }


def to_mihomo_proxy(
    profile: VlessProfile | HysteriaProfile, address_override: str | None = None
) -> dict[str, Any]:
    """Профиль → прокси-запись конфига mihomo (Clash Meta)."""
    address = address_override or profile.address
    name = getattr(profile, "name", "") or f"{address}:{profile.port}"

    if isinstance(profile, HysteriaProfile):
        proxy: dict[str, Any] = {
            "name": name,
            "type": "hysteria2",
            "server": address,
            "port": profile.port,
            "password": profile.auth,
            "udp": True,
        }
        if profile.sni or profile.address:
            proxy["sni"] = profile.sni or profile.address
        if profile.insecure:
            proxy["skip-cert-verify"] = True
        if profile.pin_sha256:
            proxy["fingerprint"] = profile.pin_sha256
        if profile.obfs:
            proxy["obfs"] = "salamander"
            proxy["obfs-password"] = profile.obfs_password
        return proxy

    protocol = profile.protocol
    if protocol in ("wireguard", "amnezia"):
        raise ValueError(
            f"Протокол {protocol} не поддерживается ядром mihomo"
        )
    if protocol == "shadowsocks":
        return {
            "name": name,
            "type": "ss",
            "server": address,
            "port": profile.port,
            "cipher": profile.security or "aes-128-gcm",
            "password": profile.uuid,
            "udp": True,
        }
    if protocol == "hysteria":
        return {
            "name": name,
            "type": "hysteria2",
            "server": address,
            "port": profile.port,
            "password": profile.uuid,
            "udp": True,
        }
    if protocol == "trojan":
        proxy = {
            "name": name,
            "type": "trojan",
            "server": address,
            "port": profile.port,
            "password": profile.uuid,
            "udp": True,
        }
        if profile.sni or profile.address:
            proxy["sni"] = profile.sni or profile.address
        if profile.allow_insecure:
            proxy["skip-cert-verify"] = True
        if profile.alpn:
            proxy["alpn"] = list(profile.alpn)
        proxy["client-fingerprint"] = profile.fingerprint or "chrome"
        _transport_options(profile, proxy)
        return proxy

    # vless (и vmess-ссылки, разбираемые как vless без alterId).
    proxy = {
        "name": name,
        "type": "vless",
        "server": address,
        "port": profile.port,
        "uuid": profile.uuid,
        "udp": True,
    }
    if profile.flow:
        proxy["flow"] = profile.flow
    _tls_options(profile, proxy)
    _transport_options(profile, proxy)
    return proxy


def _rules(server_ip: str | None = None) -> list[str]:
    rules: list[str] = []
    if server_ip:
        # Трафик к самому серверу — всегда мимо прокси (иначе петля:
        # соединение к серверу пойдёт через сам сервер).
        rules.append(f"IP-CIDR,{server_ip}/32,DIRECT,no-resolve")
    rules += [f"IP-CIDR,{cidr},DIRECT,no-resolve" for cidr in PRIVATE_NETWORKS]
    rules.append(f"MATCH,{PROXY_GROUP}")
    return rules


def _server_ip(profile: VlessProfile | HysteriaProfile, address_override: str | None) -> str | None:
    for candidate in (address_override, profile.address):
        if candidate and is_ip(candidate):
            return candidate
    return None


def build_config(
    profile: VlessProfile | HysteriaProfile,
    *,
    tun: bool,
    socks_port: int = 10808,
    http_port: int = 10809,
    log_level: str = "warning",
    address_override: str | None = None,
    enable_ipv6: bool | None = None,
) -> dict[str, Any]:
    if not 1 <= socks_port <= 65535 or not 1 <= http_port <= 65535:
        raise ValueError("Порты должны быть в диапазоне 1..65535")
    if socks_port == http_port:
        raise ValueError("SOCKS и HTTP порты должны различаться")

    proxy = to_mihomo_proxy(profile, address_override)
    server_ip = _server_ip(profile, address_override)

    config: dict[str, Any] = {
        "mode": "rule",
        "log-level": log_level,
        "socks-port": int(socks_port),
        "port": int(http_port),
        "bind-address": "127.0.0.1",
        "allow-lan": False,
        "ipv6": bool(tun and (is_ipv6_supported() if enable_ipv6 is None else enable_ipv6)),
        "proxies": [proxy],
        "proxy-groups": [
            {"name": PROXY_GROUP, "type": "select", "proxies": [proxy["name"]]}
        ],
        "rules": _rules(server_ip),
        # DNS включён всегда: домен сервера резолвим сами через DoH,
        # доверяя 1.1.1.1/8.8.8.8, а не системному (потенциально
        # подменённому) резолверу. Вместе с DoH добавлены обычные
        # UDP-серверы: mihomo опрашивает все адресаты параллельно и берёт
        # первый валидный ответ, поэтому если DoH у провайдера режется,
        # резолв всё равно работает через UDP 53.
        "dns": {
            "enable": True,
            "enhanced-mode": "fake-ip" if tun else "redir-host",
            "fake-ip-range": "198.18.0.1/16",
            "default-nameserver": ["1.1.1.1", "8.8.8.8"],
            "nameserver": [
                "https://1.1.1.1/dns-query",
                "https://8.8.8.8/dns-query",
                "1.1.1.1",
                "8.8.8.8",
            ],
            "proxy-server-nameserver": [
                "https://1.1.1.1/dns-query",
                "https://8.8.8.8/dns-query",
                "1.1.1.1",
                "8.8.8.8",
            ],
        },
    }

    if tun:
        tun_config: dict[str, Any] = {
            "enable": True,
            "stack": "mixed",
            "mtu": 1500,
            "dns-hijack": ["any:53"],
            "auto-route": True,
            "auto-detect-interface": True,
        }
        if server_ip:
            # Исключаем адрес сервера из маршрутов TUN: собственный трафик
            # mihomo к серверу обязан уходить через физический интерфейс,
            # иначе он заворачивается обратно в TUN (петля) и соединение
            # падает по таймауту.
            prefix = "128" if ":" in server_ip else "32"
            tun_config["route-exclude-address"] = [f"{server_ip}/{prefix}"]
        config["tun"] = tun_config

    return config


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, (str, int, float, bool)):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"Неизвестный тип значения: {type(value)!r}")


def _dump_block(node: Any, depth: int) -> str:
    """Блочная сериализация YAML без внешних зависимостей.

    Скаляры экранируются как JSON-строки (корректный YAML double-quoted стиль).
    """
    pad = "  " * depth
    lines: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            key_text = _yaml_scalar(str(key))
            if isinstance(value, dict) and value:
                lines.append(f"{pad}{key_text}:")
                lines.append(_dump_block(value, depth + 1))
            elif isinstance(value, list) and value:
                lines.append(f"{pad}{key_text}:")
                lines.append(_dump_block(value, depth + 1))
            elif isinstance(value, dict):
                lines.append(f"{pad}{key_text}: {{}}")
            elif isinstance(value, list):
                lines.append(f"{pad}{key_text}: []")
            else:
                lines.append(f"{pad}{key_text}: {_yaml_scalar(value)}")
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, dict):
                first = True
                for key, value in item.items():
                    key_text = _yaml_scalar(str(key))
                    prefix = f"{pad}- " if first else f"{pad}  "
                    first = False
                    if isinstance(value, (dict, list)) and value:
                        lines.append(f"{prefix}{key_text}:")
                        lines.append(_dump_block(value, depth + 1))
                    elif isinstance(value, dict):
                        lines.append(f"{prefix}{key_text}: {{}}")
                    elif isinstance(value, list):
                        lines.append(f"{prefix}{key_text}: []")
                    else:
                        lines.append(f"{prefix}{key_text}: {_yaml_scalar(value)}")
            elif isinstance(item, list):
                if not item:
                    lines.append(f"{pad}- []")
                    continue
                lines.append(f"{pad}-")
                lines.append(_dump_block(item, depth + 1))
            else:
                lines.append(f"{pad}- {_yaml_scalar(item)}")
    else:
        lines.append(f"{pad}{_yaml_scalar(node)}")
    return "\n".join(line for line in lines if line is not None)


def dump_yaml(data: Any) -> str:
    """Сериализация словаря конфига в YAML-текст (без внешних зависимостей)."""
    if not isinstance(data, dict):
        raise TypeError("Корневым элементом YAML должен быть словарь")
    return _dump_block(data, 0).rstrip("\n") + "\n"


def is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False
