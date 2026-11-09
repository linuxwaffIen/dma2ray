from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from . import paths


class TrayController:
    """Runs a small GTK3 AppIndicator process and talks to it over a Unix socket."""

    def __init__(
        self,
        on_show: Callable[[], None],
        on_toggle: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self.on_show = on_show
        self.on_toggle = on_toggle
        self.on_quit = on_quit
        self._server: socket.socket | None = None
        self._client: socket.socket | None = None
        self._client_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._last_state = {"state": "stopped", "profile": ""}

    @property
    def is_active(self) -> bool:
        return (
            self._proc is not None
            and self._proc.poll() is None
            and self._client is not None
        )

    def start(self) -> bool:
        if self._proc is not None and self._proc.poll() is None:
            return self.is_active
        if self._proc is not None or self._server is not None:
            # Clean up after a helper that exited unexpectedly.
            self.stop()
        paths.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        try:
            paths.TRAY_SOCKET.unlink()
        except FileNotFoundError:
            pass
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(paths.TRAY_SOCKET))
            server.listen(2)
            server.settimeout(0.5)
        except OSError:
            server.close()
            return False
        self._server = server
        self._stop.clear()
        self._connected.clear()
        self._thread = threading.Thread(target=self._accept_loop, name="tray-accept", daemon=True)
        self._thread.start()

        log_path = paths.CACHE_DIR / "tray.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("ab", buffering=0)
        try:
            self._proc = subprocess.Popen(
                [
                    paths.python_bin(),
                    str(paths.TRAY_SCRIPT),
                    "--socket",
                    str(paths.TRAY_SOCKET),
                    "--icon",
                    "network-vpn-symbolic",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=log_handle,
                start_new_session=True,
            )
        except OSError:
            log_handle.close()
            self.stop()
            return False
        finally:
            try:
                log_handle.close()
            except Exception:
                pass

        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            if self._connected.wait(0.1):
                break
            if self._proc.poll() is not None:
                self.stop()
                return False
        if not self._connected.is_set():
            self.stop()
            return False
        if not self.is_active:
            self.stop()
            return False
        return True

    def stop(self) -> None:
        self._stop.set()
        with self._client_lock:
            client = self._client
            self._client = None
        if client is not None:
            try:
                client.close()
            except OSError:
                pass
        server = self._server
        self._server = None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except OSError:
                    pass
        try:
            paths.TRAY_SOCKET.unlink()
        except FileNotFoundError:
            pass

    def send_state(self, state: str, profile: str = "") -> None:
        self._last_state = {"state": state, "profile": profile}
        self._send(self._last_state)

    def _send(self, payload: dict) -> None:
        with self._client_lock:
            client = self._client
        if client is None:
            return
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            with self._send_lock:
                client.sendall(data)
        except OSError:
            pass

    def _accept_loop(self) -> None:
        server = self._server
        if server is None:
            return
        while not self._stop.is_set():
            try:
                client, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with self._client_lock:
                self._client = client
            self._connected.set()
            self._send(self._last_state)
            thread = threading.Thread(
                target=self._read_loop, args=(client,), name="tray-read", daemon=True
            )
            thread.start()
            # Only one tray instance is used at a time.
            while not self._stop.is_set() and client.fileno() >= 0:
                time.sleep(0.5)

    def _read_loop(self, client: socket.socket) -> None:
        reader = client.makefile("rb")
        try:
            for raw in reader:
                try:
                    message = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                command = message.get("cmd")
                if command == "show":
                    self.on_show()
                elif command == "toggle":
                    self.on_toggle()
                elif command == "quit":
                    self.on_quit()
                    return
        except OSError:
            pass
        finally:
            with self._client_lock:
                if self._client is client:
                    self._client = None
            try:
                reader.close()
            except Exception:
                pass
            try:
                client.close()
            except OSError:
                pass
