from __future__ import annotations
import json
import urllib.request
import urllib.error
from .state import Profile
import base64
import gzip
import re
import urllib.error
import urllib.request

from .hysteria import parse_hysteria2
from .vless import (
    parse_trojan,
    parse_shadowsocks,
    parse_vmess,
    parse_wireguard,
    parse_amnezia,
    parse_vless,
)
from dataclasses import dataclass, field


MAX_SUBSCRIPTION_BYTES = 5 * 1024 * 1024
USER_AGENT = "dma2ray/0.2"
SUPPORTED_PREFIXES = (
    "vless://",
    "trojan://",
    "ss://",
    "vmess://",
    "hysteria2://",
    "hy2://",
    "wireguard://",
    "amnezia://",
)
# Префиксы, которые мы знаем, но не можем распарсить (пока без парсера)
KNOWN_PREFIXES = ("tuic://",)

@dataclass
class FetchResult:
    entries: list[tuple[str, str]] = field(default_factory=list)
    unsupported: int = 0
    invalid: int = 0
    raw_count: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.entries) + self.unsupported + self.invalid


def _decode_payload(text: str) -> str:
    candidate = text.strip()
    if not candidate:
        return ""
    if "://" in candidate:
        return candidate
    compact = re.sub(r"\s+", "", candidate)
    if not compact:
        return ""
    try:
        padded = compact + "=" * (-len(compact) % 4)
        raw = base64.b64decode(padded, altchars=b"-_", validate=False)
        decoded = raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return text
    return decoded if "://" in decoded else text


def _safe_parse(parser, uri: str):
    try:
        return parser(uri)
    except Exception:
        return None


def parse_subscription(text: str) -> FetchResult:
    decoded = _decode_payload(text)
    result = FetchResult()
    seen: set[str] = set()
    for raw_line in decoded.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        lowered = line.lower()
        if lowered.startswith(SUPPORTED_PREFIXES):
            result.raw_count += 1
            if line in seen:
                continue
            seen.add(line)
            if lowered.startswith("vless://"):
                parser = parse_vless
            elif lowered.startswith("trojan://"):
                parser = parse_trojan
            elif lowered.startswith("ss://"):
                parser = parse_shadowsocks
            elif lowered.startswith("vmess://"):
                parser = parse_vmess
            elif lowered.startswith(("hysteria2://", "hy2://")):
                parser = parse_hysteria2
            elif lowered.startswith("wireguard://"):
                parser = parse_wireguard
            elif lowered.startswith("amnezia://"):
                parser = parse_amnezia
            else:
                parser = None
            profile = _safe_parse(parser, line) if parser else None
            if profile is not None:
                result.entries.append((profile.name, line))
            else:
                result.invalid += 1
                result.errors.append("Не удалось распарсить ссылку")
        elif lowered.startswith(KNOWN_PREFIXES):
            result.raw_count += 1
            result.invalid += 1
            result.errors.append("Протокол не поддерживается")
    return result


def fetch_subscription(url: str, timeout: float = 25.0) -> str:
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL подписки должен начинаться с http:// или https://")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "gzip",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status >= 400:
                raise ValueError(f"Сервер вернул HTTP {status}")
            data = response.read(MAX_SUBSCRIPTION_BYTES + 1)
            if len(data) > MAX_SUBSCRIPTION_BYTES:
                raise ValueError("Подписка больше 5 МБ")
            encoding = (response.headers.get("Content-Encoding") or "").lower()
            charset = response.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as exc:
        raise ValueError(f"HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Сеть недоступна: {exc.reason}") from exc

    if encoding == "gzip":
        try:
            data = gzip.decompress(data)
        except OSError as exc:
            raise ValueError("Не удалось распаковать gzip-ответ") from exc
    try:
        return data.decode(charset, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def fetch_and_parse(url: str, timeout: float = 25.0) -> FetchResult:
    return parse_subscription(fetch_subscription(url, timeout))
