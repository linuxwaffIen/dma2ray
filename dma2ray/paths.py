from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_ID = "io.github.dma2ray.Dma2ray"
APP_NAME = "dma2ray"
APP_TITLE = "Dma2ray"
VERSION = "0.2.0"

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
CORE_PATH = CORE_BIN_DIR / "xray"
LOG_FILE = CACHE_DIR / "xray.log"
CONFIG_FILE = CACHE_DIR / "config.json"
PRIV_SOCKET = RUNTIME_DIR / "privileged.sock"
TRAY_SOCKET = RUNTIME_DIR / "tray.sock"
ICON_NAME = "io.github.dma2ray.Dma2ray"

# Каталоги установки кода (помимо дерева исходников / dist-каталога сборки).
_INSTALL_ROOTS = (
    Path("/usr/lib") / APP_NAME,
    _home() / ".local" / "lib" / APP_NAME,
)


def _locate(*candidates: Path) -> Path:
    """Первый существующий кандидат: исходники → dist сборки → установка."""
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


# Helper-скрипты. В скомпилированном бинарнике __file__ указывает внутрь
# dist-каталога (скрипты лежат там в helpers/), затем — установочные каталоги.
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

# Старое имя проекта (до переименования в Dma2ray) — данные переносятся один раз.
_LEGACY_NAME = "vless-gtk"


def _migrate_legacy() -> None:
    """Переносит данные установленной когда-то версии vless-gtk в dma2ray."""
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
    # Ярлык автозапуска со старым именем.
    old_auto = _xdg("XDG_CONFIG_HOME", ".config") / "autostart" / f"{_LEGACY_NAME}.desktop"
    new_auto = _xdg("XDG_CONFIG_HOME", ".config") / "autostart" / f"{APP_NAME}.desktop"
    if old_auto.is_file() and not new_auto.exists():
        try:
            old_auto.rename(new_auto)
            # Внутри старый Exec указывает на vless-gtk — переписываем на новый.
            from . import autostart

            if "X-GNOME-Autostart-enabled=true" in new_auto.read_text("utf-8"):
                new_auto.write_text(autostart.desktop_entry(), "utf-8")
        except OSError:
            pass


def ensure_dirs() -> None:
    _migrate_legacy()
    for directory, mode in (
        (CONFIG_DIR, 0o700),
        (DATA_DIR, 0o700),
        (STATE_DIR, 0o700),
        (CACHE_DIR, 0o700),
        (RUNTIME_DIR, 0o700),
        (CORE_BIN_DIR, 0o755),
    ):
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.chmod(mode)
        except OSError:
            pass


def install_user_icon() -> Path:
    """Install the app icon into the user's hicolor theme (for the tray)."""
    target_dir = _xdg("XDG_DATA_HOME", ".local/share") / "icons" / "hicolor" / "scalable" / "apps"
    target = target_dir / f"{ICON_NAME}.svg"
    try:
        if ICON_FILE.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_bytes() != ICON_FILE.read_bytes():
                target.write_bytes(ICON_FILE.read_bytes())
    except OSError:
        pass
    return target
