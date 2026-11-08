from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field, replace
from urllib.parse import parse_qsl, unquote, urlsplit


class VlessError(ValueError):
    pass


SUPPORTED_NETWORKS = {
    "tcp",
    "raw",
    "ws",
    "grpc",
    "httpupgrade",
    "xhttp",
    "kcp",
}
REMOVED_NETWORKS = {
    "http": (
        "Транспорт HTTP/2 удалён в Xray 26. Попросите у провайдера ссылку "
        "с type=xhttp."
    ),
    "h2": (
        "Транспорт HTTP/2 удалён в Xray 26. Попросите у провайдера ссылку "
        "с type=xhttp."
    ),
    "http2": (
        "Транспорт HTTP/2 удалён в Xray 26. Попросите у провайдера ссылку "
        "с type=xhttp."
    ),
    "quic": (
        "Транспорт QUIC удалён в Xray 26. Попросите у провайдера ссылку "
        "с type=xhttp."
    ),
}
SUPPORTED_SECURITY = {"none", "tls", "reality", "xtls"}


@dataclass(frozen=True)
class VlessProfile:
    uuid: str
    address: str
    port: int
    name: str
    security: str = "none"
    network: str = "tcp"
    flow: str = ""
    sni: str = ""
    alpn: list[str] = field(default_factory=list)
    fingerprint: str = ""
    allow_insecure: bool = False
    public_key: str = ""
    short_id: str = ""
    spider_x: str = "/"
    host_header: str = ""
    path: str = "/"
    service_name: str = ""
    header_type: str = "none"
    mode: str = ""
    seed: str = ""
    quic_security: str = "none"
    quic_key: str = ""
    extra: dict[str, str] = field(default_factory=dict)
    protocol: str = "vless"

    @property
    def endpoint(self) -> str:
        host = f"[{self.address}]" if ":" in self.address else self.address
        return f"{host}:{self.port}"

    @property
    def transport_label(self) -> str:
        label = self.network.upper()
        if self.network in ("tcp", "raw") and self.header_type == "http":
            label = "TCP/HTTP"
        if self.network == "xhttp" and self.mode:
            label += f"/{self.mode}"
        return label

    @property
    def security_label(self) -> str:
        if self.security == "reality":
            return "REALITY"
        if self.security in ("tls", "xtls"):
            return "TLS"
        return "NONE"

    def detail(self) -> str:
        return f"{self.endpoint} · {self.transport_label} · {self.security_label}"

    def to_xray_stream(self) -> dict:
        network = "tcp" if self.network == "raw" else self.network
        stream: dict = {"network": network}
        security = "tls" if self.security == "xtls" else self.security
        if security in ("tls", "reality"):
            stream["security"] = security
        if security == "tls":
            tls: dict = {"serverName": self.sni or self.address}
            if self.allow_insecure:
                tls["allowInsecure"] = True
            if self.alpn:
                tls["alpn"] = list(self.alpn)
            if self.fingerprint:
                tls["fingerprint"] = self.fingerprint
            stream["tlsSettings"] = tls
        elif security == "reality":
            stream["realitySettings"] = {
                "serverName": self.sni or self.address,
                "fingerprint": self.fingerprint or "chrome",
                "publicKey": self.public_key,
                "shortId": self.short_id,
                "spiderX": self.spider_x or "/",
            }

        if network == "ws":
            ws: dict = {"path": self.path or "/"}
            if self.host_header:
                ws["host"] = self.host_header
            stream["wsSettings"] = ws
        elif network == "httpupgrade":
            upgrade: dict = {"path": self.path or "/"}
            if self.host_header:
                upgrade["host"] = self.host_header
            stream["httpupgradeSettings"] = upgrade
        elif network == "grpc":
            grpc: dict = {"serviceName": self.service_name}
            if self.mode.lower() in ("multi", "multimode"):
                grpc["multiMode"] = True
            stream["grpcSettings"] = grpc
        elif network == "xhttp":
            xhttp: dict = {"path": self.path or "/"}
            if self.host_header:
                xhttp["host"] = self.host_header
            if self.mode:
                xhttp["mode"] = self.mode
            stream["xhttpSettings"] = xhttp
        elif network == "kcp":
            kcp: dict = {"header": {"type": self.header_type or "none"}}
            if self.seed:
                kcp["seed"] = self.seed
            stream["kcpSettings"] = kcp
        elif network == "tcp" and self.header_type == "http":
            request: dict = {"path": [self.path or "/"]}
            if self.host_header:
                request["headers"] = {"Host": _split_hosts(self.host_header)}
            stream["tcpSettings"] = {"header": {"type": "http", "request": request}}

        return stream

    def to_xray_outbound(self, address_override: str | None = None) -> dict:
        address = address_override or self.address
        if self.protocol == "trojan":
            outbound: dict = {
                "tag": "proxy",
                "protocol": "trojan",
                "settings": {
                    "server": address,
                    "server_port": self.port,
                    "password": self.uuid,
                },
            }
            outbound["streamSettings"] = self.to_xray_stream()
            return outbound
        if self.protocol == "shadowsocks":
            return {
                "tag": "proxy",
                "protocol": "shadowsocks",
                "settings": {
                    "server": address,
                    "server_port": self.port,
                    "method": self.security or "aes-128-gcm",
                    "password": self.uuid,
                },
            }
        if self.protocol == "wireguard":
            return {
                "tag": "proxy",
                "protocol": "wireguard",
                "settings": {
                    "secret": self.uuid,
                },
            }
        if self.protocol == "hysteria" or self.protocol == "hysteria2":
            return {
                "tag": "proxy",
                "protocol": "hysteria",
                "settings": {
                    "server": address,
                    "port": self.port,
                    "password": self.uuid,
                },
            }
        if self.protocol == "amnezia":
            return {
                "tag": "proxy",
                "protocol": "amnezia",
                "settings": {
                    "server": address,
                    "port": self.port,
                    "password": self.uuid,
                },
            }
        user: dict = {"id": self.uuid, "encryption": "none"}
        if self.flow:
            user["flow"] = self.flow
        return {
            "tag": "proxy",
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": address,
                        "port": self.port,
                        "users": [user],
                    }
                ]
            },
            "streamSettings": self.to_xray_stream(),
        }


def parse_trojan(uri: str) -> VlessProfile:
    uri = uri.strip()
    if not uri.lower().startswith("trojan://"):
        raise VlessError("Ссылка должна начинаться с trojan://")
    rest = uri[len("trojan://"):]
    auth, _, hostport = rest.partition("@")
    password = unquote(auth)
    if not password:
        raise VlessError("В ссылке отсутствует пароль Trojan")
    hostport = hostport.split("?", 1)[0]
    host, _, port_str = hostport.rpartition(":")
    if not host:
        raise VlessError("В ссылке отсутствует адрес сервера")
    try:
        port = int(port_str or "443")
    except ValueError as exc:
        raise VlessError(f"Некорректный порт: {exc}") from exc
    profile = replace(
        VlessProfile(
            uuid=password,
            address=host,
            port=port,
            name=f"trojan://{host}:{port}",
            security="tls",
            network="tcp",
        ),
        protocol="trojan",
    )
    return profile


def parse_shadowsocks(uri: str) -> VlessProfile:
    uri = uri.strip()
    if not uri.lower().startswith("ss://"):
        raise VlessError("Ссылка должна начинаться с ss://")
    payload = uri[len("ss://"):]
    method_password, _, rest = payload.partition("@")
    method, _, password = method_password.partition(":")
    hostport = rest.split("?", 1)[0]
    host, _, port_str = hostport.rpartition(":")
    try:
        port = int(port_str or "443")
    except ValueError as exc:
        raise VlessError(f"Некорректный порт: {exc}") from exc
    return replace(
        VlessProfile(
            uuid=password,
            address=host,
            port=port,
            name=f"ss://{host}:{port}",
            security=method or "aes-128-gcm",
        ),
        protocol="shadowsocks",
    )


def parse_vmess(uri: str) -> VlessProfile:
    uri = uri.strip()
    if not uri.lower().startswith("vmess://"):
        raise VlessError("Ссылка должна начинаться с vmess://")
    payload = uri[len("vmess://"):]
    padded = payload + "=" * (-len(payload) % 4)
    raw = base64.b64decode(padded, altchars="-_", validate=False)
    data = json.loads(raw.decode("utf-8"))
    uuid = str(data.get("id") or data.get("uuid") or "")
    address = str(data.get("add") or data.get("address") or "")
    port = int(data.get("port") or 443)
    return replace(
        VlessProfile(
            uuid=uuid,
            address=address,
            port=port,
            name=str(data.get("ps") or f"{address}:{port}"),
        ),
        protocol="vless",
    )


def parse_hysteria2(uri: str) -> VlessProfile:
    uri = uri.strip().lower()
    if not (uri.startswith("hysteria2://") or uri.startswith("hy2://")):
        raise VlessError("Ссылка должна начинаться с hysteria2:// или hy2://")
    rest = uri.split("://", 1)[1]
    authority, _, query = rest.partition("?")
    host, _, port_str = authority.rpartition(":")
    try:
        port = int(port_str or "443")
    except ValueError as exc:
        raise VlessError(f"Некорректный порт: {exc}") from exc
    q = {k: v for k, v in parse_qsl(query, keep_blank_values=True)}
    password = q.get("p") or q.get("password") or ""
    return replace(
        VlessProfile(
            uuid=password,
            address=host,
            port=port,
            name=f"hysteria2://{host}:{port}",
            security="none",
        ),
        protocol="hysteria",
    )


def parse_wireguard(uri: str) -> VlessProfile:
    uri = uri.strip()
    if not uri.lower().startswith("wireguard://"):
        raise VlessError("Ссылка должна начинаться с wireguard://")
    rest = uri[len("wireguard://"):]
    auth, _, hostport = rest.partition("@")
    public_key = unquote(auth)
    if not public_key:
        raise VlessError("В ссылке отсутствует публичный ключ WireGuard")
    hostport = hostport.split("?", 1)[0]
    host, _, port_str = hostport.rpartition(":")
    if not host:
        raise VlessError("В ссылке отсутствует адрес сервера")
    try:
        port = int(port_str or "51820")
    except ValueError as exc:
        raise VlessError(f"Некорректный порт: {exc}") from exc
    return replace(
        VlessProfile(
            uuid=public_key,
            address=host,
            port=port,
            name=f"wireguard://{host}:{port}",
            security="none",
        ),
        protocol="wireguard",
    )


def parse_amnezia(uri: str) -> VlessProfile:
    uri = uri.strip()
    if not uri.lower().startswith("amnezia://"):
        raise VlessError("Ссылка должна начинаться с amnezia://")
    rest = uri[len("amnezia://"):]
    auth, _, hostport = rest.partition("@")
    password = unquote(auth)
    if not password:
        raise VlessError("В ссылке отсутствует пароль Amnezia")
    hostport = hostport.split("?", 1)[0]
    host, _, port_str = hostport.rpartition(":")
    if not host:
        raise VlessError("В ссылке отсутствует адрес сервера")
    try:
        port = int(port_str or "443")
    except ValueError as exc:
        raise VlessError(f"Некорректный порт: {exc}") from exc
    return replace(
        VlessProfile(
            uuid=password,
            address=host,
            port=port,
            name=f"amnezia://{host}:{port}",
            security="none",
        ),
        protocol="amnezia",
    )


def _split_hosts(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _first(query: dict[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = query.get(name)
        if value not in (None, ""):
            return value
    return default


def _as_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def parse_vless(uri: str) -> VlessProfile:
    uri = uri.strip()
    if not uri.lower().startswith("vless://"):
        raise VlessError("Ссылка должна начинаться с vless://")
    try:
        parts = urlsplit(uri)
        host = (parts.hostname or "").strip()
        raw_port = parts.port
    except ValueError as exc:
        raise VlessError(f"Некорректная ссылка: {exc}") from exc

    uuid = unquote(parts.username or "").strip()
    if not uuid:
        raise VlessError("В ссылке отсутствует UUID")
    if len(uuid) > 64 or any(char.isspace() for char in uuid):
        raise VlessError("Некорректный UUID")

    if not host:
        raise VlessError("В ссылке отсутствует адрес сервера")
    host = host.strip("[]")

    try:
        port = int(443 if raw_port is None else raw_port)
    except (TypeError, ValueError) as exc:
        raise VlessError("Некорректный порт") from exc
    if not 1 <= port <= 65535:
        raise VlessError("Порт должен быть в диапазоне 1..65535")

    query = {key.lower(): value for key, value in parse_qsl(parts.query, keep_blank_values=True)}

    network = _first(query, "type", "network", default="tcp").lower()
    if network in ("splithttp", "split-http"):
        network = "xhttp"
    if network in REMOVED_NETWORKS:
        raise VlessError(REMOVED_NETWORKS[network])
    if network not in SUPPORTED_NETWORKS:
        raise VlessError(f"Неподдерживаемый транспорт: {network}")

    security = _first(query, "security", default="none").lower()
    if security not in SUPPORTED_SECURITY:
        raise VlessError(f"Неподдерживаемый тип безопасности: {security}")
    if security == "reality" and not _first(query, "pbk", "publickey"):
        raise VlessError("Для REALITY нужен публичный ключ (pbk)")

    name = unquote(parts.fragment or "").strip() or f"{host}:{port}"
    alpn = [item for item in _first(query, "alpn").replace(" ", ",").split(",") if item]
    header_type = _first(query, "headertype", "header", default="none").lower()

    return VlessProfile(
        uuid=uuid,
        address=host,
        port=port,
        name=name,
        security=security,
        network=network,
        flow=_first(query, "flow"),
        sni=_first(query, "sni", "servername"),
        alpn=alpn,
        fingerprint=_first(query, "fp", "fingerprint"),
        allow_insecure=_as_bool(_first(query, "allowinsecure", "insecure")),
        public_key=_first(query, "pbk", "publickey"),
        short_id=_first(query, "sid", "shortid"),
        spider_x=_first(query, "spx", "spiderx", default="/") or "/",
        host_header=_first(query, "host"),
        path=_first(query, "path", default="/") or "/",
        service_name=_first(query, "servicename", "service"),
        header_type=header_type or "none",
        mode=_first(query, "mode"),
        seed=_first(query, "seed"),
        quic_security=_first(query, "quicsecurity", default="none") or "none",
        quic_key=_first(query, "key"),
        extra=query,
    )
