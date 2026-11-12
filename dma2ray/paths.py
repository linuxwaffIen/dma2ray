from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

from .icons import APP_ICON_SVG, ICONS, TRAY_ICONS

APP_ID = "io.github.dma2ray.Dma2ray"
APP_NAME = "dma2ray"
APP_TITLE = "Dma2ray"
VERSION = "0.2.1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def python_bin() -> str:
    """Интерпретатор для запуска helper-скриптов (privileged, tray).

    В скомпилированном бинарнике sys.executable указывает на несуществующий
    <dist>/python, поэтому берём системный python3. При запуске из исходников
    возвращает текущий интерпретатор, как раньше.
    """
    if "__compiled__" in globals():
        return shutil.which("python3") or sys.executable
    return sys.executable


def _home() -> Path:
    return Path.home()


def _xdg(env: str, fallback: str) -> Path:
    value = os.environ.get(env)
    return Path(value).expanduser() if value else _home() / fallback


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / APP_NAME
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / APP_NAME
STATE_DIR = _xdg("XDG_STATE_HOME", ".local/state") / APP_NAME
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache") / APP_NAME
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", str(CACHE_DIR / "run"))) / APP_NAME

STATE_FILE = CONFIG_DIR / "state.json"
CORE_BIN_DIR = DATA_DIR / "bin"


def current_arch() -> str:
    return platform.machine().lower()


def core_arch_dir(arch: str | None = None) -> Path:
    return CORE_BIN_DIR / (arch or current_arch())


def core_dir(kernel_type: str = "xray", arch: str | None = None) -> Path:
    """Каталог ядра: bin/<arch>/xray или bin/<arch>/amnezia."""
    kind = "amnezia" if kernel_type.startswith("amnezia") else "xray"
    return core_arch_dir(arch) / kind


CORE_PATH = core_dir("xray") / "xray"


def core_path(kernel_type: str = "xray", arch: str | None = None) -> Path:
    if kernel_type == "xray" and arch is None:
        return CORE_PATH
    return core_dir(kernel_type, arch) / "xray"

LOG_FILE = CACHE_DIR / "xray.log"
CONFIG_FILE = CACHE_DIR / "config.json"
HY_PATH = CORE_BIN_DIR / "hysteria"
HY_CONFIG_FILE = CACHE_DIR / "config-hy.yaml"
PRIV_SOCKET = RUNTIME_DIR / "privileged.sock"
TRAY_SOCKET = RUNTIME_DIR / "tray.sock"
ICON_NAME = "io.github.dma2ray.Dma2ray"

_INSTALL_ROOTS = (
    Path("/usr/lib") / APP_NAME,
    _home() / ".local" / "lib" / APP_NAME,
)


def _locate(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


PRIV_SCRIPT = _locate(
    Path(__file__).resolve().parent / "privileged.py",
    PROJECT_ROOT / "helpers" / "privileged.py",
    *(_root / "dma2ray" / "privileged.py" for _root in _INSTALL_ROOTS),
)
TRAY_SCRIPT = _locate(
    Path(__file__).resolve().parent / "tray_helper.py",
    PROJECT_ROOT / "helpers" / "tray_helper.py",
    *(_root / "dma2ray" / "tray_helper.py" for _root in _INSTALL_ROOTS),
)
ICON_FILE = _locate(
    PROJECT_ROOT / "data" / f"{ICON_NAME}.svg",
    *(_root / "data" / f"{ICON_NAME}.svg" for _root in _INSTALL_ROOTS),
)


def icons_dir() -> Path:
    return DATA_DIR / "icons"


def ensure_icons() -> Path:
    directory = icons_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        for name, svg in ICONS.items():
            target = directory / f"{name}.svg"
            data = svg.encode("utf-8")
            if not target.exists() or target.read_bytes() != data:
                target.write_bytes(data)
    except OSError:
        pass
    return directory


def app_icon_path() -> Path:
    if ICON_FILE.exists():
        return ICON_FILE
    ensure_icons()
    return icons_dir() / f"{ICON_NAME}.svg"


def tray_icon_path(state: str) -> Path:
    ensure_icons()
    return icons_dir() / f"dma2ray-tray-{state}.svg"

_LEGACY_NAME = "vless-gtk"


def _migrate_legacy() -> None:
    for old, new in (
        (_xdg("XDG_CONFIG_HOME", ".config") / _LEGACY_NAME, CONFIG_DIR),
        (_xdg("XDG_DATA_HOME", ".local/share") / _LEGACY_NAME, DATA_DIR),
        (_xdg("XDG_STATE_HOME", ".local/state") / _LEGACY_NAME, STATE_DIR),
        (_xdg("XDG_CACHE_HOME", ".cache") / _LEGACY_NAME, CACHE_DIR),
    ):
        if not old.is_dir() or new.exists():
            continue
        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)
        except OSError:
            pass
    old_auto = _xdg("XDG_CONFIG_HOME", ".config") / "autostart" / f"{_LEGACY_NAME}.desktop"
    new_auto = _xdg("XDG_CONFIG_HOME", ".config") / "autostart" / f"{APP_NAME}.desktop"
    if old_auto.is_file() and not new_auto.exists():
        try:
            old_auto.rename(new_auto)
            from . import autostart

            if "X-GNOME-Autostart-enabled=true" in new_auto.read_text("utf-8"):
                new_auto.write_text(autostart.desktop_entry(), "utf-8")
        except OSError:
            pass


def _migrate_core_layout() -> None:
    """Старые bin/xray, bin/amnezia → bin/<arch>/xray, bin/<arch>/amnezia."""
    target_xray = core_dir("xray")
    target_amnezia = core_dir("amnezia-xray")

    legacy = CORE_BIN_DIR / "xray"
    if legacy.is_file():
        temporary = CORE_BIN_DIR / ".xray-legacy"
        try:
            legacy.replace(temporary)
            target_xray.mkdir(parents=True, exist_ok=True)
            temporary.replace(target_xray / "xray")
        except OSError:
            pass
    elif legacy.is_dir():
        try:
            if target_xray.exists():
                for item in legacy.iterdir():
                    destination = target_xray / item.name
                    if not destination.exists():
                        item.replace(destination)
            else:
                target_xray.parent.mkdir(parents=True, exist_ok=True)
                legacy.replace(target_xray)
        except OSError:
            pass

    legacy_amnezia = CORE_BIN_DIR / "amnezia"
    if legacy_amnezia.is_dir() and not target_amnezia.exists():
        try:
            target_amnezia.parent.mkdir(parents=True, exist_ok=True)
            legacy_amnezia.replace(target_amnezia)
        except OSError:
            pass

    for name in ("geoip.dat", "geosite.dat", "LICENSE", "README.md"):
        source = CORE_BIN_DIR / name
        if source.is_file():
            try:
                target_xray.mkdir(parents=True, exist_ok=True)
                source.replace(target_xray / name)
            except OSError:
                pass


def ensure_dirs() -> None:
    _migrate_legacy()
    _migrate_core_layout()
    for directory, mode in (
        (CONFIG_DIR, 0o700),
        (DATA_DIR, 0o700),
        (STATE_DIR, 0o700),
        (CACHE_DIR, 0o700),
        (RUNTIME_DIR, 0o700),
        (CORE_BIN_DIR, 0o755),
        (core_arch_dir(), 0o755),
        (core_dir("xray"), 0o755),
        (core_dir("amnezia-xray"), 0o755),
    ):
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.chmod(mode)
        except OSError:
            pass


def install_user_icon() -> Path:
    source = app_icon_path()
    hicolor = _xdg("XDG_DATA_HOME", ".local/share") / "icons" / "hicolor"
    app_target = hicolor / "scalable" / "apps" / f"{ICON_NAME}.svg"
    try:
        app_target.parent.mkdir(parents=True, exist_ok=True)
        if not app_target.exists() or app_target.read_bytes() != source.read_bytes():
            app_target.write_bytes(source.read_bytes())
        status_dir = hicolor / "scalable" / "status"
        status_dir.mkdir(parents=True, exist_ok=True)
        for state in ("stopped", "starting", "running"):
            src = tray_icon_path(state)
            dst = status_dir / f"dma2ray-tray-{state}.svg"
            if src.exists() and (not dst.exists() or dst.read_bytes() != src.read_bytes()):
                dst.write_bytes(src.read_bytes())
    except OSError:
        pass
    return app_target
