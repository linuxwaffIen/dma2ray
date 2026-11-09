from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote, urlsplit


class HysteriaError(ValueError):
    pass


@dataclass(frozen=True)
class HysteriaProfile:
    auth: str
    address: str
    port: int
    name: str
    sni: str = ""
    insecure: bool = False
    pin_sha256: str = ""
    obfs: str = ""
    obfs_password: str = ""
    protocol: str = "hysteria2"

    @property
    def endpoint(self) -> str:
        host = f"[{self.address}]" if ":" in self.address else self.address
        return f"{host}:{self.port}"

    def detail(self) -> str:
        return f"{self.endpoint} · QUIC · HYSTERIA2"


def parse_hysteria2(uri: str) -> HysteriaProfile:
    uri = uri.strip()
    if not uri.lower().startswith(("hysteria2://", "hy2://")):
        raise HysteriaError("Ссылка должна начинаться с hysteria2:// или hy2://")
    try:
        parts = urlsplit(uri)
        host = (parts.hostname or "").strip("[]")
        port = parts.port or 443
    except ValueError as exc:
        # сюда попадает и port hopping вида host:20000-30000
        raise HysteriaError(f"Некорректный адрес или порт: {exc}") from exc
    if not host:
        raise HysteriaError("В ссылке отсутствует адрес сервера")
    auth = unquote(parts.username or "")
    if parts.password is not None:
        auth += ":" + unquote(parts.password)
    if not auth:
        raise HysteriaError("В ссылке отсутствует пароль")
    q = {k.lower(): v for k, v in parse_qsl(parts.query, keep_blank_values=True)}
    obfs = q.get("obfs", "")
    if obfs and obfs != "salamander":
        raise HysteriaError(f"Неподдерживаемая обфускация: {obfs}")
    return HysteriaProfile(
        auth=auth,
        address=host,
        port=port,
        name=unquote(parts.fragment).strip() or f"{host}:{port}",
        sni=q.get("sni", ""),
        insecure=q.get("insecure", "").lower() in ("1", "true"),
        pin_sha256=q.get("pinsha256", ""),
        obfs=obfs,
        obfs_password=q.get("obfs-password", ""),
    )


def build_hysteria_config(
    p: HysteriaProfile,
    *,
    tun: bool,
    socks_port: int,
    http_port: int,
    address_override: str | None = None,
) -> dict:
    server_ip = address_override or p.address
    host = f"[{server_ip}]" if ":" in server_ip else server_ip
    tls: dict = {"sni": p.sni or p.address}
    if p.insecure:
        tls["insecure"] = True
    if p.pin_sha256:
        tls["pinSHA256"] = p.pin_sha256
    cfg: dict = {
        "server": f"{host}:{p.port}",
        "auth": p.auth,
        "tls": tls,
        "socks5": {"listen": f"127.0.0.1:{socks_port}"},
        "http": {"listen": f"127.0.0.1:{http_port}"},
    }
    if p.obfs:
        cfg["obfs"] = {"type": "salamander", "salamander": {"password": p.obfs_password}}
        return cfg
    if tun:
        v4_ex = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16"]
        v6_ex = ["fc00::/7", "fe80::/10"]
        if ":" in server_ip:
            v6_ex.append(server_ip + "/128")  # иначе QUIC пойдёт сам в себя
        else:
            v4_ex.append(server_ip + "/32")
        cfg["tun"] = {
            "name": "hytun",
            "mtu": 1500,
            "timeout": "5m",
            "address": {
                "ipv4": "100.100.100.101/30",
                "ipv6": "2001::ffff:ffff:ffff:fff1/126",
            },
            "route": {
                "ipv4": ["0.0.0.0/0"],
                "ipv6": ["2000::/3"],
                "ipv4Exclude": v4_ex,
                "ipv6Exclude": v6_ex,
            },
        }

def parse_any(uri: str):
    """Единая точка входа: vless:// или hysteria2://."""
    from .vless import parse_vless

    if uri.strip().lower().startswith(("hysteria2://", "hy2://")):
        return parse_hysteria2(uri)
    return parse_vless(uri)
