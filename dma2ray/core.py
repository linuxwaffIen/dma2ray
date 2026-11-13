from __future__ import annotations

import json
import os
import re
import select
import shutil

try:
    import pty
except ImportError:  # Windows: pseudo-terminal fallback недоступен
    pty = None
import signal
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .config import build_config, dump_yaml, is_ip
from .state import Profile, Store
from .hysteria import parse_any
SYSTEM_DIR = Path("/usr/libexec/dma2ray")
SYSTEM_HELPER = SYSTEM_DIR / "dma2ray-helper"
SYSTEM_CORE = SYSTEM_DIR / "mihomo"

class CoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class CoreStatus:
    state: str  # stopped | starting | running | error
    profile_id: str | None = None
    tun: bool = False
    detail: str = ""
    error: str | None = None
    log: str = ""


def _tail(path: Path, limit: int = 16000) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


def _read_since(path: Path, offset: int, limit: int = 8000) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            return handle.read(limit).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _is_tty_auth_error(path: Path, offset: int) -> bool:
    """pkexec без polkit-агента не может открыть /dev/tty и падает сразу."""
    text = _read_since(path, offset).lower()
    markers = (
        "controlling terminal",
        "textual authentication agent",
        "/dev/tty",
        "no such device or address",
    )
    return any(marker in text for marker in markers)


def _looks_like_password_prompt(buffer: bytes) -> bool:
    text = buffer.decode("utf-8", errors="replace")[-400:]
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text).lower()
    stripped = text.rstrip()
    if not stripped or stripped.endswith("\n"):
        return False
    return ("password" in text or "пароль" in text) and stripped.endswith(":")


def _clean_prompt(buffer: bytes) -> str:
    text = buffer.decode("utf-8", errors="replace")
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    relevant = [
        line
        for line in lines
        if any(
            k in line.lower()
            for k in ("authenticat", "авториз", "root", "password", "пароль")
        )
    ]
    return "\n".join(relevant[-2:]) if relevant else (lines[-1] if lines else "Password:")


def _read_pty(fd: int, timeout: float) -> bytes:
    try:
        ready, _, _ = select.select([fd], [], [], timeout)
    except (OSError, ValueError):
        return b""
    if not ready:
        return b""
    try:
        return os.read(fd, 4096)
    except OSError:
        return b""


def _close_fd(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _drain_tty(fd: int, log_handle) -> None:
    try:
        while True:
            try:
                ready, _, _ = select.select([fd], [], [], 1.0)
            except (OSError, ValueError):
                break
            if not ready:
                continue
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            try:
                log_handle.write(chunk)
            except Exception:
                pass
    finally:
        _close_fd(fd)
        try:
            log_handle.close()
        except Exception:
            pass


class _PtyProcess:
    """Минимальная обёртка над pid из pty.fork() (нужен только интерфейс Popen)."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self._code: int | None = None

    def poll(self) -> int | None:
        if self._code is not None:
            return self._code
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            self._code = 0
            return self._code
        if pid == 0:
            return None
        try:
            self._code = os.waitstatus_to_exitcode(status)
        except ValueError:
            self._code = 1
        return self._code

    def wait(self, timeout: float | None = None) -> int:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            code = self.poll()
            if code is not None:
                return code
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired("pkexec", timeout)
            time.sleep(0.05)

    def terminate(self) -> None:
        try:
            os.kill(self.pid, signal.SIGTERM)
        except OSError:
            pass

    def kill(self) -> None:
        try:
            os.kill(self.pid, signal.SIGKILL)
        except OSError:
            pass


def preferred_kernel_type(store: Store, parsed: object | None = None) -> str:
    """Ядро одно — mihomo. Функция сохранена для совместимости вызовов."""
    return "mihomo"


def find_core(store: Store, parsed: object | None = None) -> Path | None:
    """Locate the mihomo binary: explicit path, downloaded core, then PATH."""
    configured = store.core_path()
    if configured.is_file():
        try:
            configured.resolve().relative_to(paths.CORE_BIN_DIR.resolve())
        except ValueError:
            return configured
    candidate = paths.core_path()
    if candidate.is_file():
        return candidate
    if configured.is_file():
        return configured
    found = shutil.which("mihomo")
    return Path(found) if found else None


class _HelperClient:
    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.reader = sock.makefile("rb")
        self.lock = threading.Lock()

    def request(self, payload: dict, timeout: float = 30.0) -> dict:
        with self.lock:
            try:
                self.sock.settimeout(timeout)
                data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
                self.sock.sendall(data)
                line = self.reader.readline()
            except (OSError, TimeoutError) as exc:
                raise CoreError(f"Нет ответа от privileged helper: {exc}") from exc
            if not line:
                raise CoreError("Privileged helper закрыл соединение")
            try:
                response = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise CoreError("Некорректный ответ privileged helper") from exc
            if not isinstance(response, dict):
                raise CoreError("Некорректный ответ privileged helper")
            return response

    def close(self) -> None:
        try:
            self.reader.close()
        except Exception:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class CoreManager:
    """Owns the mihomo process and, for TUN mode, the privileged helper."""

    def __init__(self, store: Store, on_status, ask_password=None) -> None:
        self.store = store
        self.on_status = on_status
        self.ask_password = ask_password
        self._lock = threading.RLock()
        self._status = CoreStatus("stopped")
        self._direct_proc: subprocess.Popen | None = None
        self._helper: _HelperClient | None = None
        self._helper_proc: subprocess.Popen | None = None
        self._helper_key: tuple[str, str, str] | None = None
        self._intentional = True
        self._starting = False
        self._monitors = 0
        self._cancel = threading.Event()

    @property
    def status(self) -> CoreStatus:
        return self._status

    @property
    def is_running(self) -> bool:
        return self._status.state == "running"

    # --------------------------------------------------------------- public
    def start(self, profile: Profile, tun: bool) -> None:
        with self._lock:
            if self._starting:
                return
            self._starting = True
            self._intentional = False
            self._cancel.clear()
        thread = threading.Thread(
            target=self._start_worker, args=(profile, tun), name="mihomo-start", daemon=True
        )
        thread.start()

    def stop(self) -> None:
        # Cancel a pending pkexec prompt or config check as soon as possible.
        self._cancel.set()
        thread = threading.Thread(target=self._stop_worker, name="mihomo-stop", daemon=True)
        thread.start()

    def shutdown(self) -> None:
        self._cancel.set()
        with self._lock:
            self._intentional = True
            self._stop_internal(shutdown_helper=True)
            self._status = CoreStatus("stopped")

    def log_text(self, limit: int = 16000) -> str:
        text = _tail(paths.LOG_FILE, limit)
        if text:
            return text
        return self._status.log

    # -------------------------------------------------------------- workers
    def _emit(self, status: CoreStatus) -> None:
        self._status = status
        try:
            self.on_status(status)
        except Exception:
            pass

    def _start_worker(self, profile: Profile, tun: bool) -> None:
        try:
            with self._lock:
                if self._cancel.is_set() or self._intentional:
                    self._emit(CoreStatus("stopped"))
                    return
                self._stop_internal(shutdown_helper=True, notify=False)
                self._emit(
                    CoreStatus("starting", profile.id, tun, "Проверка mihomo…")
                )
                try:
                    self._raise_if_cancelled()
                    parsed = parse_any(profile.uri)
                    core = self._core_path(parsed)
                    self._check_core(core)
                    self._emit(
                        CoreStatus("starting", profile.id, tun, "Проверка доступности сервера…")
                    )
                    # Только проверка доступности; IP-подстановку не делаем:
                    # домен сервера mihomo резолвит сам через DoH (см. dns в
                    # конфиге), системный DNS может быть подменён.
                    self._resolve(parsed.address, parsed.port)
                    self._raise_if_cancelled()
                    settings = dict(self.store.settings)
                    config = build_config(
                        parsed,
                        tun=tun,
                        socks_port=int(settings["socks_port"]),
                        http_port=int(settings["http_port"]),
                        log_level=str(settings["log_level"]),
                    )
                    self._write_config(config)
                    self._emit(
                       CoreStatus("starting", profile.id, tun, "Проверка конфигурации…")
                    )
                    self._validate(core)
                    self._raise_if_cancelled()
                    paths.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
                    if tun:
                        self._start_tun(core)
                    else:
                        self._start_direct(core)
                    self._emit(CoreStatus("running", profile.id, tun, "Подключено"))
                except Exception as exc:
                        self._stop_internal(shutdown_helper=True, notify=False)
                        if self._cancel.is_set() or self._intentional:
                            self._emit(CoreStatus("stopped"))
                            return
                        message = str(exc) or exc.__class__.__name__
                        self._emit(
                            CoreStatus(
                                "error",
                                profile.id,
                                tun,
                                "Ошибка запуска",
                                message,
                                _tail(paths.LOG_FILE),
                            )
                        )
        finally:
                with self._lock:
                    self._starting = False

    def _raise_if_cancelled(self) -> None:
        if self._cancel.is_set():
            raise CoreError("Запуск отменён")

    def _stop_worker(self) -> None:
        with self._lock:
            self._intentional = True
            self._stop_internal(shutdown_helper=False)
            self._emit(CoreStatus("stopped"))

    # --------------------------------------------------------------- direct
    def _start_direct(self, core: Path) -> None:
        log_handle = paths.LOG_FILE.open("wb", buffering=0)
        try:
            proc = subprocess.Popen(
                [str(core), "-d", str(paths.MIHOMO_DIR), "-f", str(paths.CONFIG_FILE)],
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            log_handle.close()
            raise CoreError(f"Не удалось запустить mihomo: {exc}") from exc
        finally:
            try:
                log_handle.close()
            except Exception:
                pass
        time.sleep(0.9)
        code = proc.poll()
        if code is not None:
            raise CoreError(
                f"mihomo завершился с кодом {code}\n{_tail(paths.LOG_FILE)}".strip()
            )
        self._direct_proc = proc
        thread = threading.Thread(
            target=self._monitor_direct, args=(proc,), name="mihomo-monitor", daemon=True
        )
        thread.start()

    def _monitor_direct(self, proc: subprocess.Popen) -> None:
        code = proc.wait()
        with self._lock:
            if self._intentional or self._direct_proc is not proc:
                return
            self._direct_proc = None
            self._emit(
                CoreStatus(
                    "error",
                    self._status.profile_id,
                    self._status.tun,
                    "mihomo неожиданно завершился",
                    f"Код выхода: {code}",
                    _tail(paths.LOG_FILE),
                )
            )

    # ------------------------------------------------------------------ tun
    def _start_tun(self, core: Path) -> None:
        self._emit(
            CoreStatus(
                "starting",
                self._status.profile_id,
                True,
                "Запуск TUN (может потребоваться пароль)…",
            )
        )
        self._ensure_helper(core)
        assert self._helper is not None
        response = self._helper.request({"cmd": "start"}, timeout=45)
        if not response.get("ok"):
            log = response.get("log") or _tail(paths.LOG_FILE)
            error = response.get("error") or "mihomo не запустился"
            raise CoreError(f"{error}\n{log}".strip())
        thread = threading.Thread(
            target=self._monitor_tun, name="mihomo-tun-monitor", daemon=True
        )
        thread.start()

    def _helper_command(self, core: Path) -> tuple[list[str], bool]:
        getuid = getattr(os, "getuid", lambda: 0)
        getgid = getattr(os, "getgid", lambda: 0)
        geteuid = getattr(os, "geteuid", lambda: 0)
        run_as_root = geteuid() == 0
        use_system = (
            not run_as_root and SYSTEM_HELPER.is_file() and SYSTEM_CORE.is_file()
        )
        target_core = SYSTEM_CORE if use_system else core
        args = [
            "--socket",
            str(paths.PRIV_SOCKET),
            "--core",
            str(target_core),
            "--dir",
            str(paths.MIHOMO_ROOT_DIR),
            "--config",
            str(paths.CONFIG_FILE),
            "--log",
            str(paths.LOG_FILE),
            "--uid",
            str(getuid()),
            "--gid",
            str(getgid()),
        ]
        if run_as_root:
            command = [paths.python_bin(), str(paths.PRIV_SCRIPT), *args]
        else:
            pkexec = shutil.which("pkexec")
            if not pkexec:
                raise CoreError(
                    "Для TUN нужен pkexec (polkit). Установите polkit "
                    "или запустите приложение от root."
                )
            if use_system:
                command = [pkexec, str(SYSTEM_HELPER), *args]
            else:
                command = [pkexec, paths.python_bin(), str(paths.PRIV_SCRIPT), *args]
        return command, run_as_root

    def _ensure_helper(self, core: Path) -> None:
        use_system = (
            os.geteuid() != 0 and SYSTEM_HELPER.is_file() and SYSTEM_CORE.is_file()
        )
        if use_system:
            core = SYSTEM_CORE  # root запускает только свою копию ядра

        key = (str(core), str(paths.MIHOMO_ROOT_DIR), str(paths.CONFIG_FILE), str(paths.LOG_FILE))
        if self._helper is not None and self._helper_key == key:
            try:
                response = self._helper.request({"cmd": "status"}, timeout=5)
                if response.get("ok"):
                    return
            except CoreError:
                self._close_helper(shutdown=True)

        self._close_helper(shutdown=True)
        try:
            paths.PRIV_SOCKET.unlink()
        except FileNotFoundError:
            pass

        command, run_as_root = self._helper_command(core)
        helper_log = paths.CACHE_DIR / "helper.log"
        helper_log.parent.mkdir(parents=True, exist_ok=True)
        try:
            start_offset = helper_log.stat().st_size
        except OSError:
            start_offset = 0

        use_tty = pty is not None and not run_as_root
        proc, sock = self._spawn_and_connect(command, helper_log, use_tty=use_tty)

        self._helper_proc = proc
        sock.settimeout(45)
        self._helper = _HelperClient(sock)
        self._helper_key = key

    def _spawn_and_connect(
        self, command: list[str], helper_log: Path, *, use_tty: bool
    ) -> tuple[object, socket.socket]:
        master: int | None = None
        proc: object | None = None
        log_handle = helper_log.open("ab", buffering=0)
        try:
            if use_tty:
                proc, master = self._popen_tty(command)
            else:
                try:
                    proc = subprocess.Popen(
                        command,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=log_handle,
                    )
                except OSError as exc:
                    raise CoreError(
                        f"Не удалось запустить privileged helper: {exc}"
                    ) from exc
            sock = self._wait_helper_socket(proc, helper_log, master, log_handle)
        except BaseException:
            if proc is not None:
                self._terminate_proc(proc)
            _close_fd(master)
            try:
                log_handle.close()
            except Exception:
                pass
            raise

        if master is not None:
            threading.Thread(
                target=_drain_tty,
                args=(master, log_handle),
                name="pkexec-tty",
                daemon=True,
            ).start()
        else:
            try:
                log_handle.close()
            except Exception:
                pass
        return proc, sock

    @staticmethod
    def _popen_tty(command: list[str]) -> tuple[object, int]:
        if pty is None:  # pragma: no cover - Windows
            raise CoreError("Псевдотерминал недоступен на этой платформе")
        pid, master = pty.fork()
        if pid == 0:  # pragma: no cover - выполняется в дочернем процессе
            try:
                os.execvp(command[0], command)
            except OSError:
                os._exit(127)
        return _PtyProcess(pid), master

    @staticmethod
    def _terminate_proc(proc) -> None:
        try:
            proc.terminate()
        except OSError:
            pass
        try:
            proc.wait(timeout=3)
        except (subprocess.TimeoutExpired, OSError):
            try:
                proc.kill()
            except OSError:
                pass

    def _wait_helper_socket(
        self,
        proc,
        helper_log: Path,
        master: int | None,
        log_handle,
    ) -> socket.socket:
        deadline = time.monotonic() + 120
        prompt_buffer = b""
        secret = b""
        while time.monotonic() < deadline:
            if self._cancel.is_set():
                raise CoreError("Запуск отменён")
            code = proc.poll()
            if code is not None:
                detail = _tail(helper_log)
                raise CoreError(
                    "Авторизация отменена или privileged helper завершился"
                    + (f"\n{detail}" if detail else "")
                )
            if master is not None:
                chunk = _read_pty(master, 0.2)
                if chunk:
                    if secret:
                        chunk = chunk.replace(secret, b"***")
                    try:
                        log_handle.write(chunk)
                    except Exception:
                        pass
                    prompt_buffer = (prompt_buffer + chunk)[-4000:]
                    if _looks_like_password_prompt(prompt_buffer):
                        password = (
                            self.ask_password(_clean_prompt(prompt_buffer))
                            if self.ask_password is not None
                            else None
                        )
                        if password is None:
                            raise CoreError("Авторизация отменена")
                        secret = password.encode("utf-8")
                        try:
                            os.write(master, secret + b"\n")
                        except OSError as exc:
                            raise CoreError(
                                f"Не удалось передать пароль: {exc}"
                            ) from exc
                        prompt_buffer = b""
            try:
                candidate = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                candidate.settimeout(2.0)
                candidate.connect(str(paths.PRIV_SOCKET))
                return candidate
            except OSError:
                try:
                    candidate.close()
                except Exception:
                    pass
                if master is None:
                    time.sleep(0.2)
        raise CoreError("Истекло время ожидания авторизации pkexec (120 с)")

    def _monitor_tun(self) -> None:
        while True:
            time.sleep(2.0)
            with self._lock:
                helper = self._helper
                if helper is None or self._intentional:
                    return
                profile_id = self._status.profile_id
            try:
                response = helper.request({"cmd": "status"}, timeout=6)
            except CoreError as exc:
                with self._lock:
                    if self._intentional:
                        return
                    self._emit(
                        CoreStatus(
                            "error",
                            profile_id,
                            True,
                            "Соединение с helper потеряно",
                            str(exc),
                            _tail(paths.LOG_FILE),
                        )
                    )
                return
            if not response.get("running"):
                with self._lock:
                    if self._intentional:
                        return
                    message = response.get("error") or "mihomo остановился"
                    log = response.get("log") or _tail(paths.LOG_FILE)
                    self._emit(
                        CoreStatus(
                            "error",
                            profile_id,
                            True,
                            "Соединение разорвано",
                            message,
                            log,
                        )
                    )
                return

    def _close_helper(self, shutdown: bool) -> None:
        helper = self._helper
        self._helper = None
        self._helper_key = None
        if helper is not None:
            if shutdown:
                try:
                    helper.request({"cmd": "shutdown"}, timeout=12)
                except CoreError:
                    pass
            helper.close()
        proc = self._helper_proc
        self._helper_proc = None
        if proc is not None:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    proc.terminate()
                except OSError:
                    pass
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:
                        proc.kill()
                    except OSError:
                        pass

    # -------------------------------------------------------------- stopping
    def _stop_internal(self, shutdown_helper: bool, notify: bool = False) -> None:
        # NB: _intentional is NOT set here. It marks a user-requested stop and
        # is set by stop()/shutdown(); setting it here would make a failed
        # start look intentional and report "stopped" instead of "error".
        proc = self._direct_proc
        self._direct_proc = None
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                try:
                    proc.terminate()
                except OSError:
                    pass
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    try:
                        proc.kill()
                    except OSError:
                        pass
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
        if self._helper is not None:
            try:
                self._helper.request({"cmd": "stop"}, timeout=15)
            except CoreError:
                pass
        if shutdown_helper:
            self._close_helper(shutdown=True)

    # ---------------------------------------------------------------- checks
    def _core_path(self, parsed: object | None = None) -> Path:
        found = find_core(self.store, parsed)
        if found is not None:
            return found
        raise CoreError(
            "mihomo не найден. Скачайте его в «Настройки → Ядра → Скачать» "
            "или укажите путь к существующему бинарнику mihomo."
        )

    @staticmethod
    def _check_core(core: Path) -> None:
        if not core.is_file():
            raise CoreError(f"mihomo не найден: {core}")
        if not os.access(core, os.X_OK):
            raise CoreError(f"mihomo не исполняемый: {core}")

    def _resolve(self, host: str, port: int) -> str:
        if is_ip(host):
            return host
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise CoreError(f"Не удалось разрешить {host}: {exc}") from exc
        ipv4 = [info for info in infos if info[0] == socket.AF_INET]
        chosen = (ipv4 or infos)[0]
        return chosen[4][0]

    @staticmethod
    def _write_config(config: dict, path: Path | None = None) -> None:
        target = path or paths.CONFIG_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(dump_yaml(config))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _validate(core: Path) -> None:
        try:
            result = subprocess.run(
                [str(core), "-t", "-d", str(paths.MIHOMO_DIR), "-f", str(paths.CONFIG_FILE)],
                capture_output=True,
                text=True,
                timeout=25,
            )
        except subprocess.TimeoutExpired as exc:
            raise CoreError("Проверка конфигурации mihomo заняла слишком много времени") from exc
        if result.returncode != 0:
            output = (result.stdout + "\n" + result.stderr).strip()
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            detail = lines[-1] if lines else "неизвестная ошибка"
            raise CoreError(f"{detail}\n{output[-3000:]}")

def find_mihomo(store: Store) -> Path | None:
    return find_core(store)
