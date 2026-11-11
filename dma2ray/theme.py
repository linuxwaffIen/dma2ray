"""Material 3 theme for Dma2ray.

Один активный GtkCssProvider на APPLICATION-приоритете: light / dark / high-contrast.
Переключается по Adw.StyleManager, поэтому палитра и foreground всегда из одной
схемы. Используются только фичи GTK 4.0: named colors, alpha()/mix(), градиенты,
box-shadow, transition, @keyframes. Никаких var(), color-mix() и @media.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk


# --------------------------------------------------------------- palettes

LIGHT = {
    "primary": "#2B5CE6",
    "on_primary": "#FFFFFF",
    "primary_container": "#DCE4FF",
    "on_primary_container": "#00174B",
    "secondary": "#00696E",
    "on_secondary": "#FFFFFF",
    "secondary_container": "#9FF1F5",
    "on_secondary_container": "#002022",
    "tertiary": "#7A4FD0",
    "tertiary_container": "#EBDDFF",
    "on_tertiary_container": "#26005B",
    "error": "#BA1A1A",
    "on_error": "#FFFFFF",
    "error_container": "#FFDAD6",
    "on_error_container": "#410002",
    "success": "#146C2E",
    "on_success": "#FFFFFF",
    "success_container": "#A6F2B8",
    "on_success_container": "#00210C",
    "warning": "#7A5900",
    "on_warning": "#FFFFFF",
    "warning_container": "#FFDF9E",
    "on_warning_container": "#261A00",
    "surface": "#FAF8FF",
    "surface_container_lowest": "#FFFFFF",
    "surface_container_low": "#F4F3FA",
    "surface_container": "#EEEDF4",
    "surface_container_high": "#E8E7EF",
    "surface_container_highest": "#E2E2E9",
    "on_surface": "#1A1B21",
    "on_surface_variant": "#45464F",
    "outline": "#767680",
    "outline_variant": "#C6C6D0",
    "inverse_surface": "#2F3036",
    "inverse_on_surface": "#F1F0F7",
    "card_bg": "#FFFFFF",
    "shadow": "#000000",
}

DARK = {
    "primary": "#B4C5FF",
    "on_primary": "#002B75",
    "primary_container": "#003FA8",
    "on_primary_container": "#DCE4FF",
    "secondary": "#4DD9E0",
    "on_secondary": "#003739",
    "secondary_container": "#004F52",
    "on_secondary_container": "#9FF1F5",
    "tertiary": "#D6BAFF",
    "tertiary_container": "#5C2FB0",
    "on_tertiary_container": "#EBDDFF",
    "error": "#FFB4AB",
    "on_error": "#690005",
    "error_container": "#93000A",
    "on_error_container": "#FFDAD6",
    "success": "#6DD58C",
    "on_success": "#003919",
    "success_container": "#00522C",
    "on_success_container": "#A6F2B8",
    "warning": "#F2C14E",
    "on_warning": "#402D00",
    "warning_container": "#5C4300",
    "on_warning_container": "#FFDF9E",
    "surface": "#111318",
    "surface_container_lowest": "#0B0E13",
    "surface_container_low": "#191C20",
    "surface_container": "#1D2024",
    "surface_container_high": "#282A2F",
    "surface_container_highest": "#33353A",
    "on_surface": "#E2E2E9",
    "on_surface_variant": "#C6C6D0",
    "outline": "#90909A",
    "outline_variant": "#45464F",
    "inverse_surface": "#E2E2E9",
    "inverse_on_surface": "#2F3036",
    "card_bg": "#191C20",
    "shadow": "#000000",
}


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c))) for c in rgb)


def _mix(a: str, b: str, t: float) -> str:
    ca, cb = _rgb(a), _rgb(b)
    return _hex(tuple(ca[i] + (cb[i] - ca[i]) * t for i in range(3)))


def _rgba(value: str, alpha: float) -> str:
    r, g, b = _rgb(value)
    return f"rgba({r},{g},{b},{alpha})"


def _ramp(base: str) -> list[str]:
    return [
        _mix(base, "#ffffff", 0.62),
        _mix(base, "#ffffff", 0.30),
        base,
        _mix(base, "#000000", 0.22),
        _mix(base, "#000000", 0.44),
    ]


def _named_colors(p: dict[str, str]) -> dict[str, str]:
    on, variant = p["on_surface"], p["on_surface_variant"]
    shade = p["shadow"]
    d = {
        "accent_bg_color": p["primary"],
        "accent_fg_color": p["on_primary"],
        "accent_color": p["primary"],
        "destructive_bg_color": p["error"],
        "destructive_fg_color": p["on_error"],
        "destructive_color": p["error"],
        "success_bg_color": p["success"],
        "success_fg_color": p["on_success"],
        "success_color": p["success"],
        "warning_bg_color": p["warning"],
        "warning_fg_color": p["on_warning"],
        "warning_color": p["warning"],
        "error_bg_color": p["error"],
        "error_fg_color": p["on_error"],
        "error_color": p["error"],
        "window_bg_color": p["surface"],
        "window_fg_color": on,
        "view_bg_color": p["card_bg"],
        "view_fg_color": on,
        "headerbar_bg_color": p["surface_container"],
        "headerbar_fg_color": on,
        "headerbar_border_color": p["outline_variant"],
        "headerbar_backdrop_color": p["surface"],
        "headerbar_shade_color": _rgba(shade, 0.14),
        "card_bg_color": p["card_bg"],
        "card_fg_color": on,
        "card_shade_color": _rgba(shade, 0.10),
        "dialog_bg_color": p["surface_container_high"],
        "dialog_fg_color": on,
        "popover_bg_color": p["surface_container"],
        "popover_fg_color": on,
        "thumbnail_bg_color": p["surface_container"],
        "thumbnail_fg_color": on,
        "sidebar_bg_color": p["surface_container_low"],
        "sidebar_fg_color": on,
        "sidebar_border_color": _rgba(on, 0.10),
        "sidebar_backdrop_color": p["surface"],
        "sidebar_shade_color": _rgba(shade, 0.10),
        "secondary_sidebar_bg_color": p["surface_container"],
        "secondary_sidebar_fg_color": on,
        "secondary_sidebar_border_color": _rgba(on, 0.10),
        "secondary_sidebar_backdrop_color": p["surface_container_low"],
        "secondary_sidebar_shade_color": _rgba(shade, 0.10),
        "shade_color": _rgba(shade, 0.12),
        "scrollbar_outline_color": _rgba(p["surface"], 0.60),
        "borders": _rgba(on, 0.14),
        # --- Material roles used by the component layer ---
        "md_primary_container": p["primary_container"],
        "md_on_primary_container": p["on_primary_container"],
        "md_secondary_container": p["secondary_container"],
        "md_on_secondary_container": p["on_secondary_container"],
        "md_tertiary": p["tertiary"],
        "md_surface_container": p["surface_container"],
        "md_surface_container_high": p["surface_container_high"],
        "md_surface_container_highest": p["surface_container_highest"],
        "md_on_surface": on,
        "md_on_surface_variant": variant,
        "md_outline": p["outline"],
        "md_outline_variant": p["outline_variant"],
        "md_success_container": p["success_container"],
        "md_on_success_container": p["on_success_container"],
        "md_warning_container": p["warning_container"],
        "md_on_warning_container": p["on_warning_container"],
        "md_error_container": p["error_container"],
        "md_on_error_container": p["on_error_container"],
        "md_inverse_surface": p["inverse_surface"],
        "md_inverse_on_surface": p["inverse_on_surface"],
        "md_shadow": shade,
        "md_fab_from": p["primary"],
        "md_fab_to": _mix(p["primary"], p["tertiary"], 0.45),
        "md_secure_from": p["success"],
        "md_secure_to": p["secondary"],
    }
    for name, base in (
        ("blue", p["primary"]),
        ("green", p["success"]),
        ("yellow", p["warning"]),
        ("orange", _mix(p["warning"], p["error"], 0.35)),
        ("red", p["error"]),
        ("purple", p["tertiary"]),
    ):
        for i, value in enumerate(_ramp(base), start=1):
            d[f"{name}_{i}"] = value
    for i, key in enumerate(
        (
            "surface_container_lowest",
            "surface_container_low",
            "surface_container_high",
            "outline_variant",
            "outline",
        ),
        start=1,
    ):
        d[f"light_{i}"] = p[key]
    for i, value in enumerate(
        (
            p["outline"],
            variant,
            _mix(on, shade, 0.30),
            p["surface_container_low"],
            p["surface_container_lowest"],
        ),
        start=1,
    ):
        d[f"dark_{i}"] = value
    return d


# ------------------------------------------------- shape / size / motion

STRUCTURAL_CSS = """
.main-headerbar { padding: 4px 6px; }

.main-switcherbar { padding: 8px 10px 10px 10px; }
.main-switcherbar button {
    min-width: 88px;
    min-height: 36px;
    padding: 6px 14px;
    border-radius: 18px;
    font-size: 0.95em;
    font-weight: 600;
    transition: background-color 180ms cubic-bezier(0.2, 0, 0, 1),
                color 180ms cubic-bezier(0.2, 0, 0, 1);
}

.connect-big {
    min-width: 96px;
    min-height: 96px;
    padding: 0;
    border-radius: 28px;
    transition: background-color 240ms cubic-bezier(0.2, 0, 0, 1),
                box-shadow 240ms cubic-bezier(0.2, 0, 0, 1);
}

@keyframes md-halo {
    0%   { box-shadow: 0 0 0 0 alpha(currentColor, 0.30); }
    70%  { box-shadow: 0 0 0 16px alpha(currentColor, 0.0); }
    100% { box-shadow: 0 0 0 0 alpha(currentColor, 0.0); }
}
.connect-busy { animation: md-halo 1500ms cubic-bezier(0.2, 0, 0, 1) infinite; }

.server-card {
    padding: 14px 16px;
    border-radius: 16px;
    transition: background-color 180ms cubic-bezier(0.2, 0, 0, 1),
                box-shadow 180ms cubic-bezier(0.2, 0, 0, 1);
}

.latency-pill {
    padding: 3px 10px;
    border-radius: 8px;
    font-size: 0.85em;
    font-weight: 700;
}
.flag-big { font-size: 26px; }
.home-status { font-size: 1.5em; font-weight: 800; }

button.suggested-action,
button.destructive-action,
button.text-button {
    min-height: 36px;
    padding: 4px 18px;
    border-radius: 18px;
    font-weight: 600;
    transition: background-color 160ms cubic-bezier(0.2, 0, 0, 1),
                box-shadow 160ms cubic-bezier(0.2, 0, 0, 1);
}
button.kernel-btn {
    min-width: 104px;
    min-height: 36px;
    padding: 4px 16px;
    border-radius: 18px;
}
.kernel-icon { padding: 10px; border-radius: 12px; }

switch {
    min-width: 50px;
    min-height: 30px;
    padding: 0;
    border-radius: 15px;
}
switch > slider {
    min-width: 22px;
    min-height: 22px;
    margin: 2px;
    border-radius: 999px;
    -gtk-icon-source: none;
    transition: background-color 160ms cubic-bezier(0.2, 0, 0, 1);
}
switch:checked > slider { min-width: 24px; min-height: 24px; margin: 1px; }
switch > image { opacity: 0; }

entry { border-radius: 10px; }

dialog, dialog-host > dialog { border-radius: 24px; }
dialog.bottom-sheet, dialog-host > dialog.bottom-sheet { border-radius: 24px 24px 0 0; }
popover > contents { border-radius: 14px; }
tooltip { border-radius: 8px; }
toast { border-radius: 16px; }

scrollbar { background-color: transparent; }
scrollbar > range > trough {
    min-width: 10px;
    min-height: 10px;
    background-color: transparent;
    border: none;
    box-shadow: none;
}
scrollbar > range > trough > slider {
    min-width: 6px;
    min-height: 6px;
    margin: 2px;
    border: none;
    border-radius: 999px;
    background-color: alpha(currentColor, 0.26);
    transition: background-color 160ms ease;
}
scrollbar > range > trough > slider:hover { background-color: alpha(currentColor, 0.44); }
scrollbar > range > trough > slider:active { background-color: alpha(currentColor, 0.62); }
"""


# ------------------------------------------------------- colour layer

COLOR_CSS = """
.main-headerbar {
    background-color: @headerbar_bg_color;
    color: @headerbar_fg_color;
    box-shadow: inset 0 -1px alpha(@md_on_surface, 0.08);
}
.main-switcherbar {
    background-color: @md_surface_container;
    box-shadow: inset 0 1px alpha(@md_on_surface, 0.08);
}
.main-switcherbar button {
    background-color: transparent;
    color: @md_on_surface_variant;
    box-shadow: none;
}
.main-switcherbar button:hover { background-color: alpha(@md_on_surface, 0.08); }
.main-switcherbar button:active { background-color: alpha(@md_on_surface, 0.12); }
.main-switcherbar button:checked {
    background-color: @md_secondary_container;
    color: @md_on_secondary_container;
}
.main-switcherbar button:checked:hover {
    background-color: mix(@md_secondary_container, @md_on_secondary_container, 0.08);
}

.connect-idle {
    background-image: linear-gradient(135deg, @md_fab_from 0%, @md_fab_to 100%);
    background-color: @accent_bg_color;
    color: @accent_fg_color;
    box-shadow: 0 1px 3px alpha(@md_shadow, 0.30),
                0 8px 20px alpha(@md_fab_to, 0.30);
}
.connect-idle:hover {
    box-shadow: 0 2px 6px alpha(@md_shadow, 0.32),
                0 12px 28px alpha(@md_fab_to, 0.38);
}
.connect-idle:active { box-shadow: 0 1px 2px alpha(@md_shadow, 0.30); }

.connect-active {
    background-image: linear-gradient(135deg, @md_secure_from 0%, @md_secure_to 100%);
    background-color: @success_bg_color;
    color: @success_fg_color;
    box-shadow: 0 1px 3px alpha(@md_shadow, 0.30),
                0 8px 22px alpha(@md_secure_to, 0.34);
}
.connect-active:hover {
    box-shadow: 0 2px 6px alpha(@md_shadow, 0.32),
                0 12px 30px alpha(@md_secure_to, 0.42);
}
.connect-active:active { box-shadow: 0 1px 2px alpha(@md_shadow, 0.30); }

.connect-busy {
    background-image: none;
    background-color: @md_surface_container_highest;
    color: @md_on_surface_variant;
}

.server-card {
    background-color: @card_bg_color;
    color: @card_fg_color;
    box-shadow: 0 0 0 1px alpha(@md_on_surface, 0.07),
                0 1px 2px alpha(@md_shadow, 0.10);
}
.server-card:hover {
    background-color: mix(@card_bg_color, @md_on_surface, 0.06);
    box-shadow: 0 0 0 1px alpha(@accent_color, 0.30),
                0 4px 14px alpha(@md_shadow, 0.16);
}
.server-card:active {
    background-color: mix(@card_bg_color, @md_on_surface, 0.10);
    box-shadow: 0 0 0 1px alpha(@accent_color, 0.40);
}

.home-status { color: @window_fg_color; }
.section-hint { color: @md_on_surface_variant; }
.error-text { color: @error_color; }
.latency-good { color: @success_color; }
.latency-ok { color: @warning_color; }
.latency-bad { color: @error_color; }
.latency-unknown { color: @md_on_surface_variant; }

.latency-pill { background-color: alpha(currentColor, 0.12); }
.latency-pill.latency-good {
    background-color: @md_success_container;
    color: @md_on_success_container;
}
.latency-pill.latency-ok {
    background-color: @md_warning_container;
    color: @md_on_warning_container;
}
.latency-pill.latency-bad {
    background-color: @md_error_container;
    color: @md_on_error_container;
}
.latency-pill.latency-unknown {
    background-color: @md_surface_container_highest;
    color: @md_on_surface_variant;
}

.card {
    box-shadow: 0 0 0 1px alpha(@md_on_surface, 0.06),
                0 1px 2px alpha(@md_shadow, 0.07);
}

button.suggested-action {
    background-image: none;
    background-color: @accent_bg_color;
    color: @accent_fg_color;
    box-shadow: none;
}
button.suggested-action:hover {
    background-color: mix(@accent_bg_color, @accent_fg_color, 0.12);
    box-shadow: 0 1px 3px alpha(@md_shadow, 0.24);
}
button.suggested-action:active {
    background-color: mix(@accent_bg_color, @accent_fg_color, 0.20);
}
button.suggested-action:disabled {
    background-color: alpha(@md_on_surface, 0.12);
    color: alpha(@md_on_surface, 0.38);
}

button.destructive-action {
    background-image: none;
    background-color: @destructive_bg_color;
    color: @destructive_fg_color;
}
button.destructive-action:hover {
    background-color: mix(@destructive_bg_color, @destructive_fg_color, 0.12);
}
button.destructive-action.flat {
    background-color: transparent;
    color: @destructive_color;
}
button.destructive-action.flat:hover {
    background-color: alpha(@destructive_color, 0.12);
}

.kernel-icon {
    background-color: @md_primary_container;
    color: @md_on_primary_container;
}

switch {
    background-color: @md_surface_container_highest;
    border: 2px solid @md_outline;
    box-shadow: none;
}
switch:checked {
    background-color: @accent_bg_color;
    border-color: @accent_bg_color;
}
switch > slider {
    background-color: @md_outline;
    background-image: none;
    box-shadow: 0 1px 2px alpha(@md_shadow, 0.25);
}
switch:checked > slider { background-color: @accent_fg_color; }
switch:disabled { opacity: 0.4; }

entry:focus-within {
    outline: 2px solid alpha(@accent_color, 0.55);
    outline-offset: -2px;
}
button:focus-visible, switch:focus-visible {
    outline: 2px solid alpha(@accent_color, 0.70);
    outline-offset: 2px;
}

toast {
    background-color: @md_inverse_surface;
    color: @md_inverse_on_surface;
    box-shadow: 0 4px 14px alpha(@md_shadow, 0.30);
}
toast label, toast button { color: @md_inverse_on_surface; }
"""


def _build(palette: dict[str, str] | None) -> bytes:
    parts = []
    if palette is not None:
        parts.append(
            "\n".join(
                f"@define-color {name} {value};"
                for name, value in _named_colors(palette).items()
            )
        )
        parts.append(COLOR_CSS)
    parts.append(STRUCTURAL_CSS)
    return "\n".join(parts).encode("utf-8")


class ThemeManager:
    """Держит ровно один активный провайдер и синхронизирует его с Adw."""

    def __init__(self) -> None:
        self._display = Gdk.Display.get_default()
        self._light = Gtk.CssProvider()
        self._light.load_from_data(_build(LIGHT))
        self._dark = Gtk.CssProvider()
        self._dark.load_from_data(_build(DARK))
        self._hc = Gtk.CssProvider()
        self._hc.load_from_data(_build(None))
        self._active: Gtk.CssProvider | None = None
        self._manager = Adw.StyleManager.get_default()
        self._manager.connect("notify::dark", self._sync)
        self._manager.connect("notify::high-contrast", self._sync)
        self._sync()

    def _sync(self, *_args) -> None:
        if self._display is None:
            return
        if self._manager.get_high_contrast():
            provider = self._hc
        elif self._manager.get_dark():
            provider = self._dark
        else:
            provider = self._light
        if provider is self._active:
            return
        if self._active is not None:
            Gtk.StyleContext.remove_provider_for_display(self._display, self._active)
        Gtk.StyleContext.add_provider_for_display(
            self._display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self._active = provider

    def dispose(self) -> None:
        if self._display is not None and self._active is not None:
            Gtk.StyleContext.remove_provider_for_display(self._display, self._active)
        self._active = None
