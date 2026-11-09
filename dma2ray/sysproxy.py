from __future__ import annotations

import os
import subprocess
from pathlib import Path
from shutil import which


class SysProxyError(RuntimeError):
    """Не удалось изменить или восстановить системные настройки прокси."""


# Состояние последнего успешного apply(): что и как было сохранено.
_saved: dict | None = None
_backend: str | None = None  # "gsettings" | "kde"
_applied = False


def is_applied() -> bool:
    return _applied


def _run(cmd: list[str], *, check: bool = True) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SysProxyError(f"Не удалось выполнить {cmd[0]}: {exc}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SysProxyError(
            detail or f"Команда завершилась с кодом {result.returncode}: {cmd[0]}"
        )
    return (result.stdout or "").strip()


def _desktop() -> str:
    return ":".join(
        part
        for part in (
            os.environ.get("XDG_CURRENT_DESKTOP", ""),
            os.environ.get("DESKTOP_SESSION", ""),
        )
        if part
    ).lower()


def _gsettings_schema(desktop: str) -> str:
    if "cinnamon" in desktop:
        return "org.cinnamon.system.proxy"
    if "mate" in desktop:
        return "org.mate.proxy"
    return "org.gnome.system.proxy"


def _sub_schema(schema: str, dotted: str) -> tuple[str, str]:
    """org.gnome.system.proxy + 'http.host' -> ('org.gnome.system.proxy.http', 'host')."""
    if "." in dotted:
        sub, key = dotted.rsplit(".", 1)
        return f"{schema}.{sub}", key
    return schema, dotted


def _gsettings_get(schema: str, dotted_key: str) -> str:
    if which("gsettings") is None:
        raise SysProxyError("gsettings не найден в PATH")
    target, key = _sub_schema(schema, dotted_key)
    return _run(["gsettings", "get", target, key])


def _gsettings_set(schema: str, dotted_key: str, value: str) -> None:
    target, key = _sub_schema(schema, dotted_key)
    _run(["gsettings", "set", target, key, value])


def _apply_gsettings(host: str, http_port: int, socks_port: int) -> dict:
    schema = _gsettings_schema(_desktop())
    # Сначала читаем текущие значения (и проверяем, что схема существует).
    saved: dict[str, str] = {"_schema": schema}
    saved["mode"] = _gsettings_get(schema, "mode")
    for sub in ("http", "https", "socks"):
        saved[f"{sub}.host"] = _gsettings_get(schema, f"{sub}.host")
        saved[f"{sub}.port"] = _gsettings_get(schema, f"{sub}.port")
    try:
        _gsettings_set(schema, "mode", "'manual'")
        for sub, port in (("http", http_port), ("https", http_port), ("socks", socks_port)):
            _gsettings_set(schema, f"{sub}.host", f"'{host}'")
            _gsettings_set(schema, f"{sub}.port", str(int(port)))
    except SysProxyError:
        _restore_gsettings(saved)  # откатываем частичное применение
        raise
    return saved


def _restore_gsettings(saved: dict) -> None:
    schema = saved.get("_schema") or "org.gnome.system.proxy"
    for key, value in saved.items():
        if key.startswith("_"):
            continue
        try:
            _gsettings_set(schema, key, value)  # ошибки отката игнорируем
        except SysProxyError:
            pass


def _kde_config() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "kioslaverc"


def _write_proxy_ini(config: Path, values: dict[str, str]) -> None:
    text = config.read_text("utf-8") if config.is_file() else ""
    lines = text.splitlines()
    out: list[str] = []
    section: str | None = None
    saw_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            out.append(line)
            if section == "Proxy Settings":
                saw_section = True
                for key, value in values.items():
                    out.append(f"{key}={value}")
            continue
        if section == "Proxy Settings" and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in values:
                continue  # уже записано новое значение
        out.append(line)
    if not saw_section:
        if out and out[-1].strip():
            out.append("")
        out.append("[Proxy Settings]")
        for key, value in values.items():
            out.append(f"{key}={value}")
    config.parent.mkdir(parents=True, exist_ok=True)
    tmp = config.with_name(config.name + ".tmp")
    tmp.write_text("\n".join(out) + "\n", "utf-8")
    os.replace(tmp, config)


def _notify_kde() -> None:
    if which("dbus-send") is None:
        return
    for method in ("org.kde.KIOSlave.ReConfiguration",):
        try:
            _run(
                [
                    "dbus-send",
                    "--session",
                    "--type=method_call",
                    "--dest=org.kde.kioslave",
                    "/KIO/Scheduler",
                    method,
                    "string:global",
                ],
                check=False,
            )
        except SysProxyError:
            pass


def _apply_kde(host: str, http_port: int, socks_port: int) -> dict:
    config = _kde_config()
    saved: dict = {"_backend": "kde", "_path": config}
    saved["_content"] = config.read_bytes() if config.is_file() else None

    writer = which("kwriteconfig6") or which("kwriteconfig5")
    if writer:
        pairs = (
            ("ProxyType", "1"),
            ("httpProxy", f"http://{host} {http_port}"),
            ("httpsProxy", f"http://{host} {http_port}"),
            ("socksProxy", f"socks://{host} {socks_port}"),
        )
        try:
            for key, value in pairs:
                _run(
                    [
                        writer,
                        "--file",
                        "kioslaverc",
                        "--group",
                        "ProxySettings",
                        "--key",
                        key,
                        value,
                    ]
                )
        except SysProxyError:
            _restore_kde(saved)
            raise
    else:
        _write_proxy_ini(
            config,
            {
                "ProxyType": "1",
                "httpProxy": f"http://{host} {http_port}",
                "httpsProxy": f"http://{host} {http_port}",
                "socksProxy": f"socks://{host} {socks_port}",
            },
        )
    _notify_kde()
    return saved


def _restore_kde(saved: dict) -> None:
    config = saved.get("_path")
    content = saved.get("_content")
    try:
        if isinstance(config, Path):
            if content is None:
                config.unlink(missing_ok=True)
            else:
                config.parent.mkdir(parents=True, exist_ok=True)
                tmp = config.with_name(config.name + ".tmp")
                tmp.write_bytes(content)
                os.replace(tmp, config)
    except OSError:
        pass
    _notify_kde()


def apply(http_port: int, socks_port: int, *, host: str = "127.0.0.1") -> None:
    """Point the desktop proxy settings at our local HTTP/SOCKS ports.

    Raises SysProxyError; the previous settings are kept for revert().
    """
    global _saved, _backend, _applied
    if _applied:
        return
    desktop = _desktop()
    if "kde" in desktop or "plasma" in desktop:
        saved = _apply_kde(host, int(http_port), int(socks_port))
        backend = "kde"
    else:
        saved = _apply_gsettings(host, int(http_port), int(socks_port))
        backend = "gsettings"
    _saved = saved
    _backend = backend
    _applied = True


def revert() -> None:
    """Restore the proxy settings saved by apply(). Best-effort."""
    global _saved, _backend, _applied
    if not _applied:
        return
    saved, backend = _saved, _backend
    _saved = None
    _backend = None
    _applied = False
    if saved is None:
        return
    try:
        if backend == "kde":
            _restore_kde(saved)
        else:
            _restore_gsettings(saved)
    except SysProxyError:
        pass


def reset_for_tests() -> None:
    """Сбросить внутреннее состояние (используется только в тестах)."""
    global _saved, _backend, _applied
    _saved = None
    _backend = None
    _applied = False
