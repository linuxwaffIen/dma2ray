from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import paths

DEFAULT_SETTINGS: dict[str, Any] = {
    "tun_enabled": True,
    "mode": "vpn",
    "socks_port": 10808,
    "http_port": 10809,
    "autostart": False,
    "tray_enabled": True,
    "auto_connect": False,
    "selected_profile_id": None,
    "core_path": "",
    "log_level": "warning",
    "close_to_tray": True,
    "ping_timeout": 4.0,
    "auto_ping": True,
    "sort_by_latency": False,
    "theme": "light",
}

LOG_LEVELS = ("debug", "info", "warning", "error")

# Режимы подключения: локальный прокси, системный прокси ОС, TUN-ВПН.
MODES = ("proxy", "system", "vpn")

# Темы интерфейса (светлая/тёмная), см. «Настройки → Тема».
THEME_VALUES = ("light", "dark")


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Profile:
    name: str
    uri: str
    id: str = field(default_factory=new_id)
    subscription_id: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Profile":
        return cls(
            id=str(raw.get("id") or new_id()),
            name=str(raw.get("name") or ""),
            uri=str(raw.get("uri") or ""),
            subscription_id=(str(raw["subscription_id"]) if raw.get("subscription_id") else None),
            created_at=float(raw.get("created_at") or time.time()),
            updated_at=float(raw.get("updated_at") or time.time()),
        )


@dataclass
class Subscription:
    name: str
    url: str
    id: str = field(default_factory=new_id)
    updated_at: float = 0.0
    last_error: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Subscription":
        return cls(
            id=str(raw.get("id") or new_id()),
            name=str(raw.get("name") or ""),
            url=str(raw.get("url") or ""),
            updated_at=float(raw.get("updated_at") or 0.0),
            last_error=(str(raw["last_error"]) if raw.get("last_error") else None),
        )


class Store:
    """Persistent application state. All calls are expected on the GTK main thread."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.STATE_FILE
        self.profiles: list[Profile] = []
        self.subscriptions: list[Subscription] = []
        self.settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self._load()

    # ------------------------------------------------------------------ io
    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        self.profiles = [
            Profile.from_dict(item)
            for item in raw.get("profiles", [])
            if isinstance(item, dict) and item.get("uri")
        ]
        self.subscriptions = [
            Subscription.from_dict(item)
            for item in raw.get("subscriptions", [])
            if isinstance(item, dict) and item.get("url")
        ]
        settings = raw.get("settings")
        raw_settings = settings if isinstance(settings, dict) else None
        if isinstance(settings, dict):
            for key, default in DEFAULT_SETTINGS.items():
                value = settings.get(key, default)
                if isinstance(default, bool) and not isinstance(value, bool):
                    value = default
                elif isinstance(default, int) and not isinstance(default, bool):
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        value = default
                elif isinstance(default, float):
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        value = default
                elif default is None and value is not None:
                    value = str(value)
                self.settings[key] = value
        self.settings["log_level"] = (
            self.settings["log_level"]
            if self.settings.get("log_level") in LOG_LEVELS
            else "warning"
        )
        self.settings["theme"] = (
            self.settings["theme"]
            if self.settings.get("theme") in THEME_VALUES
            else DEFAULT_SETTINGS["theme"]
        )
        # Миграция: старые состояния имели только tun_enabled (bool).
        if raw_settings is None or "mode" not in raw_settings:
            self.settings["mode"] = "vpn" if self.settings.get("tun_enabled") else "proxy"
        if self.settings.get("mode") not in MODES:
            self.settings["mode"] = "vpn" if self.settings.get("tun_enabled") else "proxy"
        # tun_enabled остаётся зеркалом mode для обратной совместимости.
        self.settings["tun_enabled"] = self.settings["mode"] == "vpn"
        self._sanitize()

    def _sanitize(self) -> None:
        ids = {profile.id for profile in self.profiles}
        selected = self.settings.get("selected_profile_id")
        if selected not in ids:
            self.settings["selected_profile_id"] = self.profiles[0].id if self.profiles else None
        sub_ids = {sub.id for sub in self.subscriptions}
        for profile in self.profiles:
            if profile.subscription_id not in sub_ids:
                profile.subscription_id = None
        for key, default in DEFAULT_SETTINGS.items():
            self.settings.setdefault(key, default)

    def save(self) -> None:
        self._sanitize()
        payload = {
            "version": 1,
            "profiles": [asdict(profile) for profile in self.profiles],
            "subscriptions": [asdict(sub) for sub in self.subscriptions],
            "settings": self.settings,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.parent.chmod(0o700)
        except OSError:
            pass
        fd, tmp_name = tempfile.mkstemp(prefix=".state-", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, self.path)
        finally:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass

    # ------------------------------------------------------------- profiles
    def get_profile(self, profile_id: str | None) -> Profile | None:
        if not profile_id:
            return None
        return next((profile for profile in self.profiles if profile.id == profile_id), None)

    @property
    def selected_profile(self) -> Profile | None:
        return self.get_profile(self.settings.get("selected_profile_id"))

    def select_profile(self, profile_id: str | None) -> None:
        if profile_id and not self.get_profile(profile_id):
            return
        self.settings["selected_profile_id"] = profile_id
        self.save()

    def find_profile_by_uri(self, uri: str) -> Profile | None:
        return next((profile for profile in self.profiles if profile.uri == uri), None)

    def add_profile(self, name: str, uri: str, subscription_id: str | None = None) -> Profile:
        existing = self.find_profile_by_uri(uri)
        if existing:
            if name and name != existing.name:
                existing.name = name
                existing.updated_at = time.time()
            if subscription_id:
                existing.subscription_id = subscription_id
            if not self.settings.get("selected_profile_id"):
                self.settings["selected_profile_id"] = existing.id
            self.save()
            return existing
        profile = Profile(
            name=name or uri.split("@")[-1][:80],
            uri=uri,
            subscription_id=subscription_id,
        )
        self.profiles.append(profile)
        if not self.settings.get("selected_profile_id"):
            self.settings["selected_profile_id"] = profile.id
        self.save()
        return profile

    def rename_profile(self, profile_id: str, name: str) -> None:
        profile = self.get_profile(profile_id)
        if profile and name.strip():
            profile.name = name.strip()
            profile.updated_at = time.time()
            self.save()

    def remove_profile(self, profile_id: str) -> None:
        self.profiles = [profile for profile in self.profiles if profile.id != profile_id]
        self._sanitize()
        self.save()

    # -------------------------------------------------------- subscriptions
    def get_subscription(self, sub_id: str) -> Subscription | None:
        return next((sub for sub in self.subscriptions if sub.id == sub_id), None)

    def add_subscription(self, name: str, url: str) -> Subscription:
        sub = Subscription(name=name.strip() or url, url=url.strip())
        self.subscriptions.append(sub)
        self.save()
        return sub

    def remove_subscription(self, sub_id: str) -> None:
        self.subscriptions = [sub for sub in self.subscriptions if sub.id != sub_id]
        self.profiles = [
            profile for profile in self.profiles if profile.subscription_id != sub_id
        ]
        self._sanitize()
        self.save()

    def replace_subscription_profiles(
        self, sub_id: str, items: list[tuple[str, str]], error: str | None = None
    ) -> int:
        sub = self.get_subscription(sub_id)
        if not sub:
            return 0
        selected_uri = self.selected_profile.uri if self.selected_profile else None
        self.profiles = [
            profile for profile in self.profiles if profile.subscription_id != sub_id
        ]
        added = 0
        seen: set[str] = set()
        for name, uri in items:
            if uri in seen:
                continue
            seen.add(uri)
            self.profiles.append(
                Profile(name=name, uri=uri, subscription_id=sub_id)
            )
            added += 1
        sub.updated_at = time.time()
        sub.last_error = error
        if selected_uri:
            match = self.find_profile_by_uri(selected_uri)
            if match:
                self.settings["selected_profile_id"] = match.id
        self._sanitize()
        self.save()
        return added

    def set_subscription_error(self, sub_id: str, error: str) -> None:
        sub = self.get_subscription(sub_id)
        if sub:
            sub.last_error = error
            sub.updated_at = time.time()
            self.save()

    def profiles_for_subscription(self, sub_id: str) -> list[Profile]:
        return [profile for profile in self.profiles if profile.subscription_id == sub_id]

    # ------------------------------------------------------------- settings
    @property
    def mode(self) -> str:
        value = self.settings.get("mode")
        return value if value in MODES else "proxy"

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"Неизвестный режим: {mode}")
        self.settings["mode"] = mode
        self.settings["tun_enabled"] = mode == "vpn"
        self.save()

    def set_setting(self, key: str, value: Any) -> None:
        self.settings[key] = value
        if key == "mode" and value in MODES:
            self.settings["tun_enabled"] = value == "vpn"
        self.save()

    def core_path(self) -> Path:
        configured = str(self.settings.get("core_path") or "").strip()
        if configured:
            return Path(configured).expanduser()
        return paths.CORE_PATH
