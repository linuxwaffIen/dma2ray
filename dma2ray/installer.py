from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from . import paths

XRAY_RELEASE_BASE = "https://github.com/XTLS/Xray-core/releases/latest/download"
AMNEZIA_RELEASE_BASE = "https://github.com/amnezia-vpn/xray-core/releases/latest/download"
USER_AGENT = "dma2ray/0.2"

SUPPORTED_ARCHS = frozenset(
    {
        "x86_64",
        "amd64",
        "aarch64",
        "arm64",
        "armv7l",
        "armv7",
        "armv6l",
        "i386",
        "i486",
        "i586",
        "i686",
        "riscv64",
    }
)

ASSETS_XRAY = {
    "x86_64": "Xray-linux-64.zip",
    "amd64": "Xray-linux-64.zip",
    "aarch64": "Xray-linux-arm64-v8a.zip",
    "arm64": "Xray-linux-arm64-v8a.zip",
    "armv7l": "Xray-linux-arm32-v7a.zip",
    "armv7": "Xray-linux-arm32-v7a.zip",
    "armv6l": "Xray-linux-arm32-v6.zip",
    "i386": "Xray-linux-32.zip",
    "i486": "Xray-linux-32.zip",
    "i586": "Xray-linux-32.zip",
    "i686": "Xray-linux-32.zip",
    "riscv64": "Xray-linux-riscv64.zip",
}

ASSETS_AMNEZIA = dict(ASSETS_XRAY)

Progress = Callable[[float, str], None]


def asset_name(kernel_type: str, arch: str | None = None) -> str:
    machine = (arch or platform.machine()).lower()
    assets = ASSETS_AMNEZIA if kernel_type == "amnezia" else ASSETS_XRAY
    asset = assets.get(machine)
    if not asset:
        raise RuntimeError(f"Нет сборки {kernel_type} для архитектуры {machine}")
    return asset


def _release_base(kernel_type: str) -> str:
    return AMNEZIA_RELEASE_BASE if kernel_type == "amnezia" else XRAY_RELEASE_BASE


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


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
                    progress(min(fraction, 0.95), "Скачивание Xray-core…")
        if total and downloaded != total:
            raise RuntimeError("Загрузка прервана")


def _expected_sha256(dgst_url: str) -> str:
    with urllib.request.urlopen(_request(dgst_url), timeout=30) as response:
        text = response.read().decode("utf-8", errors="replace")
    match = re.search(r"SHA2-256\s*=\s*([0-9a-fA-F]{64})", text)
    if not match:
        raise RuntimeError("Не найден SHA2-256 в файле контрольных сумм")
    return match.group(1).lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_core(
    progress: Progress | None = None, arch: str | None = None, kernel_type: str = "xray"
) -> Path:
    asset = asset_name(kernel_type, arch)
    paths.CORE_BIN_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dma2ray-core-", dir=str(paths.CACHE_DIR)) as tmp:
        tmpdir = Path(tmp)
        archive = tmpdir / asset
        base_url = f"{_release_base(kernel_type)}/{asset}"
        label = "Amnezia" if kernel_type == "amnezia" else "Xray-core"
        if progress:
            progress(0.02, f"Загрузка {label}…")
        _download(base_url, archive, progress)
        if progress:
            progress(0.96, "Проверка контрольной суммы…")
        expected = _expected_sha256(base_url + ".dgst")
        actual = _sha256(archive)
        if actual != expected:
            raise RuntimeError(
                f"Контрольная сумма не совпала: ожидалось {expected[:12]}…, получено {actual[:12]}…"
            )

        extract_dir = tmpdir / "extract"
        extract_dir.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            allowed = {"xray", "geoip.dat", "geosite.dat", "LICENSE", "README.md"}
            for info in bundle.infolist():
                name = Path(info.filename).name
                if name not in allowed:
                    continue
                target = extract_dir / name
                with bundle.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)

        new_binary = extract_dir / "xray"
        if not new_binary.exists():
            raise RuntimeError(f"В архиве {label} не найден бинарник xray")
        new_binary.chmod(0o755)
        staged = paths.CORE_BIN_DIR / ".xray.new"
        shutil.copy2(new_binary, staged)
        staged.chmod(0o755)
        os.replace(staged, paths.CORE_PATH)

        for extra in ("geoip.dat", "geosite.dat", "LICENSE", "README.md"):
            source = extract_dir / extra
            if source.exists():
                shutil.copy2(source, paths.CORE_BIN_DIR / extra)

    if progress:
        progress(1.0, f"Xray-core для {arch or platform.machine()} установлен")
    return paths.CORE_PATH
