from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

from . import paths

AUTOSTART_FILE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / f"{paths.APP_NAME}.desktop"


def _command() -> str:
    """Команда автозапуска: скомпилированный бинарник либо исходники."""
    candidates = [
        shutil.which("dma2ray"),
        # Сборка из исходников (./build.sh).
        str(paths.PROJECT_ROOT / "dist" / "dma2ray.dist" / "dma2ray"),
        # Скомпилированный бинарник: PROJECT_ROOT — его dist-каталог.
        str(paths.PROJECT_ROOT / "dma2ray"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return f"{shlex.quote(candidate)} --minimized"
    # Запуск из дерева исходников: python -m dma2ray.
    return (
        f'env PYTHONPATH="{paths.PROJECT_ROOT}" '
        f"{shlex.quote(sys.executable)} -m dma2ray --minimized"
    )


def desktop_entry() -> str:
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.0",
            f"Name={paths.APP_TITLE}",
            "Comment=VLESS client with Xray TUN support",
            f"Exec={_command()}",
            f"Icon={paths.ICON_NAME}",
            "Terminal=false",
            "Categories=Network;",
            "MimeType=x-scheme-handler/vless;",
            "StartupNotify=false",
            "X-GNOME-Autostart-enabled=true",
            "X-XFCE-Autostart-Override=true",
            "",
        ]
    )


def is_enabled() -> bool:
    try:
        text = AUTOSTART_FILE.read_text("utf-8")
    except OSError:
        return False
    return "X-GNOME-Autostart-enabled=true" in text and "Hidden=true" not in text


def set_enabled(enabled: bool) -> None:
    if enabled:
        AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART_FILE.write_text(desktop_entry(), "utf-8")
        try:
            AUTOSTART_FILE.chmod(0o644)
        except OSError:
            pass
    else:
        try:
            AUTOSTART_FILE.unlink()
        except FileNotFoundError:
            pass
