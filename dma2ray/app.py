from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk

from . import paths
from .state import Store
from .window import MainWindow


class Dma2rayApplication(Adw.Application):
    def __init__(self, *, minimized: bool = False, pending_uris: list[str] | None = None) -> None:
        super().__init__(
            application_id=paths.APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self.minimized = minimized
        self.pending_uris = list(pending_uris or [])
        self.window: MainWindow | None = None
        self._auto_connect_done = False

    # --------------------------------------------------------------- lifecycle
    def do_activate(self) -> None:
        self._ensure_window()
        assert self.window is not None
        if self.pending_uris:
            uris = self.pending_uris
            self.pending_uris = []
            self.window.import_uris(uris)
        if not (self.minimized and self.window.tray_active):
            self.window.present()
        if self.window.tray_active:
            self.window.set_visible(not self.minimized)
        if not self._auto_connect_done:
            self._auto_connect_done = True
            if self.window.store.settings.get("auto_connect", False):
                GLib.timeout_add(800, self._auto_connect)

    def do_open(self, files, n_files: int, hint: str) -> None:
        self._ensure_window()
        assert self.window is not None
        if self.pending_uris:
            uris = self.pending_uris
            self.pending_uris = []
            self.window.import_uris(uris)
        uris = []
        for file in files:
            try:
                uri = file.get_uri()
            except Exception:
                continue
            if uri and uri.lower().startswith("vless://"):
                uris.append(uri)
        if uris:
            self.window.import_uris(uris)
        self.window.present()

    def do_shutdown(self) -> None:
        if self.window is not None:
            self.window.shutdown()
            self.window = None
        Gio.Application.do_shutdown(self)

    def _ensure_window(self) -> None:
        if self.window is not None:
            return
        paths.ensure_dirs()
        paths.install_user_icon()
        store = Store()
        self.window = MainWindow(self, store)
        self.window.set_icon_name(paths.ICON_NAME)

    def _auto_connect(self) -> bool:
        if self.window is None:
            return False
        if not self.window.core.is_running:
            profile = self.window.store.selected_profile
            if profile is not None:
                tun = self.window.store.mode == "vpn"
                self.window.core.start(profile, tun)
        return False


def _usage(program: str) -> str:
    return (
        f"Использование: {program} [--minimized] [--import VLESS_URI] [vless://...]\n"
        "\n"
        "  --minimized      запустить свёрнутым в трей\n"
        "  --import URI     импортировать ссылку vless://\n"
        "  --version        показать версию\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    if not args:
        args = ["dma2ray"]
    minimized = False
    imports: list[str] = []
    open_args: list[str] = []
    index = 1
    while index < len(args):
        arg = args[index]
        if arg == "--minimized":
            minimized = True
        elif arg in ("--version", "-V"):
            print(f"{paths.APP_TITLE} {paths.VERSION}")
            return 0
        elif arg in ("--help", "-h"):
            print(_usage(args[0]))
            return 0
        elif arg == "--import":
            if index + 1 >= len(args):
                print("--import требует ссылку", file=sys.stderr)
                return 2
            imports.append(args[index + 1])
            index += 1
        elif arg.startswith("--import="):
            imports.append(arg.split("=", 1)[1])
        elif arg.lower().startswith("vless://"):
            open_args.append(arg)
        elif arg.startswith("-"):
            print(f"Неизвестный параметр: {arg}", file=sys.stderr)
            print(_usage(args[0]), file=sys.stderr)
            return 2
        index += 1

    GLib.set_prgname(paths.APP_NAME)
    GLib.set_application_name(paths.APP_TITLE)
    app = Dma2rayApplication(minimized=minimized)
    # Pass imports as file arguments so a running instance receives them
    # through do_open() instead of silently activating without the URI.
    return app.run([args[0], *imports, *open_args])


if __name__ == "__main__":
    raise SystemExit(main())
