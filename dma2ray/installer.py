from __future__ import annotations

import gzip
import os
import platform
import shutil
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

from . import paths

RELEASE_BASE = "https://github.com/MetaCubeX/mihomo/releases/latest/download"
VERSION_URL = f"{RELEASE_BASE}/version.txt"
USER_AGENT = "dma2ray/0.2"

# Поддерживаются только три архитектуры.
# Для amd64 берём совместимую сборку v1 (базовый x86-64, без AVX и т.п.).
MIHOMO_TAGS = {
    "x86_64": "amd64-v1",
    "amd64": "amd64-v1",
    "aarch64": "arm64",
    "arm64": "arm64",
    "armv7l": "armv7",
    "armv7": "armv7",
}

SUPPORTED_ARCHS = frozenset(MIHOMO_TAGS)

Progress = Callable[[float, str], None]


def current_arch() -> str:
    return platform.machine().lower()


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def latest_tag() -> str:
    """Актуальная версия mihomo из version.txt релиза (например 'v1.19.34')."""
    with urllib.request.urlopen(_request(VERSION_URL), timeout=30) as response:
        tag = response.read().decode("utf-8", errors="replace").strip()
    if not tag.startswith("v"):
        raise RuntimeError(f"Неожиданный ответ version.txt: {tag!r}")
    return tag


def asset_name(arch: str | None = None, tag: str | None = None) -> str:
    """Имя архива ядра: mihomo-linux-<arch>-<tag>.gz."""
    machine = (arch or current_arch()).lower()
    try:
        kind = MIHOMO_TAGS[machine]
    except KeyError:
        raise RuntimeError(f"Нет сборки mihomo для архитектуры {machine}") from None
    version = tag or latest_tag()
    return f"mihomo-linux-{kind}-{version}.gz"


def _download(url: str, destination: Path, progress: Progress | None) -> None:
    with urllib.request.urlopen(_request(url), timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if progress:
                    fraction = (downloaded / total) if total else 0.0
                    progress(min(fraction, 0.95), "Скачивание mihomo…")
        if total and downloaded != total:
            raise RuntimeError("Загрузка прервана")


def install_core(progress: Progress | None = None, arch: str | None = None) -> Path:
    """Скачать mihomo для архитектуры и положить бинарник в каталог ядер."""
    machine = (arch or current_arch()).lower()
    target_dir = paths.core_dir(arch=machine)
    target_path = paths.core_path(arch=machine)
    target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dma2ray-core-", dir=str(paths.CACHE_DIR)) as tmp:
        tmpdir = Path(tmp)
        archive = tmpdir / "mihomo.gz"
        tag = latest_tag()
        asset = asset_name(machine, tag)
        base_url = f"{RELEASE_BASE}/{asset}"
        if progress:
            progress(0.02, f"Загрузка {asset}…")
        _download(base_url, archive, progress)
        if progress:
            progress(0.96, "Распаковка…")

        new_binary = tmpdir / "mihomo"
        with gzip.open(archive, "rb") as source, new_binary.open("wb") as destination:
            shutil.copyfileobj(source, destination)
        new_binary.chmod(0o755)

        staged = target_dir / ".mihomo.new"
        shutil.copy2(new_binary, staged)
        staged.chmod(0o755)
        os.replace(staged, target_path)

    if progress:
        progress(1.0, "mihomo установлен")
    return target_path
