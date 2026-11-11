"""Пресеты акцента и извлечение доминирующего цвета из обоев рабочего стола."""

from __future__ import annotations

import colorsys
import os
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio

ACCENT_PRESETS: tuple[tuple[str, str], ...] = (
    ("Синий", "#2B5CE6"),
    ("Бирюзовый", "#00838F"),
    ("Зелёный", "#2E7D32"),
    ("Янтарный", "#C77700"),
    ("Красный", "#C62828"),
    ("Розовый", "#C2185B"),
    ("Фиолетовый", "#6A35C2"),
    ("Графит", "#54606F"),
)

DEFAULT_ACCENT = "#2B5CE6"

MODE_LABELS = {
    "preset": "Пресет",
    "custom": "Свой цвет",
    "wallpaper": "Из обоев",
}


def normalize_hex(value: str | None) -> str:
    if not value:
        return DEFAULT_ACCENT
    v = value.strip()
    if not v.startswith("#"):
        v = "#" + v
    if len(v) == 4:
        v = "#" + "".join(ch * 2 for ch in v[1:])
    if len(v) != 7:
        return DEFAULT_ACCENT
    try:
        int(v[1:], 16)
    except ValueError:
        return DEFAULT_ACCENT
    return v.upper()


def _uri_to_path(raw: str) -> Path | None:
    raw = raw.strip()
    if raw.startswith("file://"):
        return Path(unquote(urlparse(raw).path))
    if raw.startswith("/"):
        return Path(os.path.expanduser(raw))
    return None


def wallpaper_path() -> Path | None:
    candidates: list[str] = []
    source = Gio.SettingsSchemaSource.get_default()
    for schema in (
        "org.gnome.desktop.background",
        "org.cinnamon.desktop.background",
        "org.mate.background",
    ):
        try:
            if source is None or source.lookup(schema, True) is None:
                continue
            settings = Gio.Settings.new(schema)
            keys = settings.list_keys()
            for key in ("picture-uri-dark", "picture-uri", "picture-filename"):
                if key in keys:
                    value = settings.get_string(key)
                    if value:
                        candidates.append(value)
        except Exception:
            continue
    try:
        out = subprocess.run(
            ["xfconf-query", "-c", "xfce4-desktop", "-p",
             "/backdrop/screen0/monitor0/workspace0/last-image"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0 and out.stdout.strip():
            candidates.append(out.stdout.strip())
    except Exception:
        pass
    for raw in candidates:
        path = _uri_to_path(raw)
        if path and path.is_file():
            return path
    return None


def extract_wallpaper_accent(path: Path | None = None) -> str | None:
    path = path or wallpaper_path()
    if path is None:
        return None
    try:
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
    except (ValueError, ImportError):
        return None
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
        if pixbuf is None:
            return None
        pixbuf = pixbuf.scale_simple(96, 96, GdkPixbuf.InterpType.BILINEAR)
    except Exception:
        return None
    if pixbuf is None:
        return None
    channels = pixbuf.get_n_channels()
    if channels < 3 or pixbuf.get_bits_per_sample() != 8:
        return None
    data = pixbuf.get_pixels()
    rowstride = pixbuf.get_rowstride()
    width, height = pixbuf.get_width(), pixbuf.get_height()
    has_alpha = pixbuf.get_has_alpha()

    buckets: dict[tuple[int, int, int], list[float]] = {}
    for y in range(height):
        row = y * rowstride
        for x in range(width):
            i = row + x * channels
            if has_alpha and data[i + 3] < 200:
                continue
            r, g, b = data[i], data[i + 1], data[i + 2]
            mx, mn = max(r, g, b), min(r, g, b)
            if mx < 40 or mn > 232:
                continue
            h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            if s < 0.22 or v < 0.25:
                continue
            key = (int(h * 16), int(s * 4), int(v * 4))
            bucket = buckets.setdefault(key, [0.0, 0.0, 0.0, 0.0])
            bucket[0] += 1.0
            bucket[1] += r
            bucket[2] += g
            bucket[3] += b
    if not buckets:
        return None

    def score(key) -> float:
        count = buckets[key][0]
        saturation = (key[1] + 0.5) / 4.0
        return count * (0.35 + saturation ** 1.6)

    best = max(buckets, key=score)
    count, rs, gs, bs = buckets[best]
    r, g, b = rs / count / 255.0, gs / count / 255.0, bs / count / 255.0
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = min(1.0, max(0.58, s))
    v = min(0.92, max(0.60, v))
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))
