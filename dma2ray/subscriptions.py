from __future__ import annotations

import base64
import gzip
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .vless import (
    VlessError,
    parse_amnezia,
    parse_hysteria2,
    parse_shadowsocks,
    parse_trojan,
    parse_vless,
    parse_vmess,
)

MAX_SUBSCRIPTION_BYTES = 5 * 1024 * 1024
USER_AGENT = "dma2ray/0.2"
SUPPORTED_PREFIXES = (
    "vless://",
    "trojan://",
    "ss://",
    "vmess://",
    "hysteria2://",
    "hy2://",
)
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
            profile = None
            parse_error: str | None = None
            if lowered.startswith("vless://"):
                profile = _safe_parse(parse_vless, line)
            elif lowered.startswith("trojan://"):
                profile = _safe_parse(parse_trojan, line)
            elif lowered.startswith("ss://"):
                profile = _safe_parse(parse_shadowsocks, line)
            elif lowered.startswith("vmess://"):
                profile = _safe_parse(parse_vmess, line)
            elif lowered.startswith("hysteria2://") or lowered.startswith("hy2://"):
                profile = _safe_parse(parse_hysteria2, line)
            if profile is not None:
                result.entries.append((profile.name, line))
            else:
                if parse_error is None:
                    parse_error = "Не удалось распарсить ссылку"
                result.invalid += 1
                result.errors.append(str(parse_error))
        elif lowered.startswith(KNOWN_PREFIXES):
            result.raw_count += 1
            result.unsupported += 1
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
