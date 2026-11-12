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
    if not (uri.lower().startswith("hysteria2://") or uri.lower().startswith("hy2://")):
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
    if not 1 <= port <= 65535:
        raise HysteriaError("Порт должен быть в диапазоне 1..65535")
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
    return cfg


def format_hysteria_config(cfg: dict) -> str:
    """Сериализация конфига Hysteria в YAML-текст (без внешних зависимостей)."""
    lines: list[str] = []
    lines.append(f"server: {cfg['server']}")
    lines.append(f"auth: {cfg['auth']}")

    tls = cfg.get("tls", {})
    if tls:
        lines.append("tls:")
        lines.append(f"  sni: {tls.get('sni', '')}")
        if tls.get("insecure"):
            lines.append("  insecure: true")
        if tls.get("pinSHA256"):
            lines.append(f"  pinSHA256: {tls['pinSHA256']}")

    socks = cfg.get("socks5", {})
    if socks:
        lines.append("socks5:")
        lines.append(f"  listen: {socks['listen']}")

    http = cfg.get("http", {})
    if http:
        lines.append("http:")
        lines.append(f"  listen: {http['listen']}")

    obfs = cfg.get("obfs")
    if obfs:
        lines.append("obfs:")
        lines.append(f"  type: {obfs.get('type')}")
        sal = obfs.get("salamander", {})
        if sal.get("password"):
            lines.append("  salamander:")
            lines.append(f"    password: {sal['password']}")

    tun = cfg.get("tun")
    if tun:
        lines.append("tun:")
        lines.append(f"  name: {tun.get('name')}")
        lines.append(f"  mtu: {tun.get('mtu')}")
        lines.append(f"  timeout: {tun.get('timeout')}")
        addr = tun.get("address", {})
        lines.append("  address:")
        lines.append(f"    ipv4: {addr.get('ipv4', '')}")
        lines.append(f"    ipv6: {addr.get('ipv6', '')}")
        route = tun.get("route", {})
        lines.append("  route:")
        lines.append("    ipv4:")
        for r in route.get("ipv4", []):
            lines.append(f"      - {r}")
        lines.append("    ipv6:")
        for r in route.get("ipv6", []):
            lines.append(f"      - {r}")
        if route.get("ipv4Exclude"):
            lines.append("    ipv4Exclude:")
            for r in route["ipv4Exclude"]:
                lines.append(f"      - {r}")
        if route.get("ipv6Exclude"):
            lines.append("    ipv6Exclude:")
            for r in route["ipv6Exclude"]:
                lines.append(f"      - {r}")
    return "\n".join(lines)


def parse_any(uri: str):
    """Единая точка входа: hysteria2:// или всё остальное (vless и т.д.)."""
    from .vless import parse_vless

    if uri.strip().lower().startswith(("hysteria2://", "hy2://")):
        return parse_hysteria2(uri)
    return parse_vless(uri)
