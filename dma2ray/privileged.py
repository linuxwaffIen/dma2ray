#!/usr/bin/env python3
"""Small privileged helper for mihomo TUN mode.

Started through pkexec. It owns the root mihomo process, writes its log and
reverts routes by stopping mihomo gracefully. It only accepts commands from
the user who started it and only uses paths fixed at startup.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import pwd
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path


def _log_tail(path: Path, limit: int = 16000) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


def _pdeathsig() -> None:  # pragma: no cover - runs in the forked child
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except Exception:
        pass


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


class Runner:
    def __init__(
        self, core: Path, workdir: Path, config: Path, log_path: Path, uid: int, gid: int
    ) -> None:
        self.core = core
        self.workdir = workdir
        self.config = config
        self.log_path = log_path
        self.uid = uid
        self.gid = gid
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()

    def status(self) -> dict:
        with self.lock:
            proc = self.proc
            running = bool(proc and proc.poll() is None)
            return {
                "ok": True,
                "running": running,
                "pid": proc.pid if running and proc else None,
                "returncode": None if running or not proc else proc.returncode,
                "log": _log_tail(self.log_path),
            }

    def start(self) -> dict:
        with self.lock:
            self._stop_locked()
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(
                    self.log_path,
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
                    0o644,
                )
                try:
                    os.fchmod(fd, 0o644)
                    os.fchown(fd, self.uid, self.gid)
                except OSError:
                    pass
                log_handle = os.fdopen(fd, "wb", buffering=0)
            except OSError as exc:
                return {"ok": False, "error": f"Не удалось открыть лог: {exc}"}

            try:
                self.proc = subprocess.Popen(
                    [str(self.core), "-d", str(self.workdir), "-f", str(self.config)],
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    preexec_fn=_pdeathsig,
                    env={
                        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                        "HOME": "/root",
                        "LANG": "C.UTF-8",
                    },
                )
            except OSError as exc:
                log_handle.close()
                return {"ok": False, "error": f"Не удалось запустить mihomo: {exc}"}
            finally:
                try:
                    log_handle.close()
                except Exception:
                    pass

            # Give mihomo a moment to create the TUN device and install routes.
            time.sleep(1.0)
            code = self.proc.poll()
            if code is not None:
                tail = _log_tail(self.log_path)
                self.proc = None
                return {
                    "ok": False,
                    "error": f"mihomo завершился с кодом {code}",
                    "log": tail,
                }
            return {
                "ok": True,
                "running": True,
                "pid": self.proc.pid,
                "log": _log_tail(self.log_path),
            }

    def stop(self) -> dict:
        with self.lock:
            self._stop_locked()
            return {"ok": True, "running": False, "log": _log_tail(self.log_path)}

    def _stop_locked(self) -> None:
        proc = self.proc
        self.proc = None
        if not proc or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            try:
                proc.terminate()
            except OSError:
                pass
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return
            time.sleep(0.1)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            try:
                proc.kill()
            except OSError:
                pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


class Helper:
    def __init__(self, args: argparse.Namespace) -> None:
        self.socket_path = Path(args.socket)
        self.uid = int(args.uid)
        self.gid = int(args.gid)
        self.runner = Runner(
            Path(args.core), Path(args.dir), Path(args.config), Path(args.log),
            self.uid, self.gid,
        )
        self.server: socket.socket | None = None
        self.stop_event = threading.Event()
        self._validate_paths()

    def _validate_paths(self) -> None:
        try:
            home = Path(pwd.getpwuid(self.uid).pw_dir)
        except KeyError:
            home = Path("/root")
        core = self.runner.core
        if not core.is_file() or not os.access(core, os.X_OK):
            raise SystemExit(f"mihomo не найден или не исполняемый: {core}")
        allowed_roots = [home, Path("/usr"), Path("/usr/local"), Path("/opt"), Path("/app")]
        if not any(_under(core, root) for root in allowed_roots):
            raise SystemExit(f"mihomo вне разрешённых каталогов: {core}")
        if not any(_under(self.runner.workdir, root) for root in allowed_roots):
            raise SystemExit(f"Рабочий каталог mihomo вне разрешённых каталогов: {self.runner.workdir}")
        if not _under(self.runner.config, home):
            raise SystemExit("Конфиг должен находиться в домашнем каталоге пользователя")
        if not _under(self.runner.log_path, home):
            raise SystemExit("Лог должен находиться в домашнем каталоге пользователя")

    def run(self) -> int:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server = server
        server.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        try:
            os.chown(self.socket_path, self.uid, self.gid)
        except OSError:
            pass
        server.listen(2)
        server.settimeout(1.0)
        try:
            while not self.stop_event.is_set():
                try:
                    client, _ = server.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                try:
                    self._handle_client(client)
                finally:
                    try:
                        client.close()
                    except OSError:
                        pass
                # The app keeps one long-lived connection. Once it goes away,
                # the app is gone too, so do not leave a root process behind.
                break
        finally:
            self.runner.stop()
            try:
                server.close()
            except OSError:
                pass
            try:
                self.socket_path.unlink()
            except FileNotFoundError:
                pass
        return 0

    def _handle_client(self, client: socket.socket) -> None:
        try:
            creds = client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            _pid, uid, _gid = struct.unpack("3i", creds)
        except OSError:
            return
        if uid not in (self.uid, 0):
            self._send(client, {"ok": False, "error": "Недостаточно прав"})
            return

        reader = client.makefile("rb")
        try:
            for raw in reader:
                if self.stop_event.is_set():
                    break
                try:
                    message = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self._send(client, {"ok": False, "error": "Некорректная команда"})
                    continue
                command = message.get("cmd")
                try:
                    if command == "start":
                        response = self.runner.start()
                    elif command == "stop":
                        response = self.runner.stop()
                    elif command == "status":
                        response = self.runner.status()
                    elif command == "shutdown":
                        self.runner.stop()
                        self._send(client, {"ok": True, "running": False})
                        self.stop_event.set()
                        return
                    else:
                        response = {"ok": False, "error": "Неизвестная команда"}
                except Exception as exc:  # keep the helper alive on unexpected errors
                    response = {"ok": False, "error": f"Внутренняя ошибка: {exc}"}
                self._send(client, response)
        finally:
            try:
                reader.close()
            except Exception:
                pass

    @staticmethod
    def _send(client: socket.socket, payload: dict) -> None:
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            client.sendall(data)
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Privileged mihomo helper for dma2ray")
    parser.add_argument("--socket", required=True)
    parser.add_argument("--core", required=True)
    parser.add_argument("--dir", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--uid", required=True)
    parser.add_argument("--gid", required=True)
    args = parser.parse_args(argv)

    if os.geteuid() != 0:
        print("privileged helper must run as root", file=sys.stderr)
        return 1

    helper = Helper(args)

    def on_signal(_signum, _frame):
        helper.stop_event.set()
        helper.runner.stop()
        try:
            helper.socket_path.unlink()
        except OSError:
            pass
        os._exit(0)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    return helper.run()


if __name__ == "__main__":
    raise SystemExit(main())
