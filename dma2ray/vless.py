from __future__ import annotations

from dataclasses import dataclass, field
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
        user: dict = {"id": self.uuid, "encryption": "none"}
        if self.flow:
            user["flow"] = self.flow
        return {
            "tag": "proxy",
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": address_override or self.address,
                        "port": self.port,
                        "users": [user],
                    }
                ]
            },
            "streamSettings": self.to_xray_stream(),
        }


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
