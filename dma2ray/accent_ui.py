"""Выбор акцента Material 3: миксин для MainWindow + фабрика кнопок с ripple."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from .accent import (
    ACCENT_PRESETS,
    DEFAULT_ACCENT,
    extract_wallpaper_accent,
    normalize_hex,
)
from .theme import ThemeManager

try:
    from .colorscience import schemes_from_seed
except Exception:  # pragma: no cover
    schemes_from_seed = None

try:
    from .widgets import RippleButton as _RippleButton
except Exception:  # pragma: no cover
    _RippleButton = None


_MODE_LABELS = {"preset": "Пресет", "custom": "Свой цвет", "wallpaper": "Из обоев"}

_TONE_ROLES = (
    ("primary", "Primary — кнопки, FAB, акценты"),
    ("primary_container", "Primary container — выделения"),
    ("secondary_container", "Secondary container — активная вкладка"),
    ("tertiary_container", "Tertiary container — градиент FAB"),
    ("surface_container_highest", "Surface — фон чипов и свитчей"),
)


def themed_button(corner_radius: float) -> Gtk.Button:
    """RippleButton, если модуль доступен; иначе обычная кнопка."""
    if _RippleButton is not None:
        try:
            return _RippleButton(corner_radius=corner_radius)
        except Exception:
            pass
    return Gtk.Button()


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def on_color(hex_color: str) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255.0 for i in (1, 3, 5))
    y = 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)
    return "#101014" if y > 0.42 else "#FFFFFF"


class AccentMixin:
    """Тема + строка «Акцентный цвет». Подмешивается перед Adw.ApplicationWindow."""

    # ------------------------------------------------------------------ theme

    def _install_css(self) -> None:
        seed = normalize_hex(self.store.settings.get("accent_color", DEFAULT_ACCENT))
        self._theme = ThemeManager(seed)
        self.connect("destroy", self._dispose_theme)

    def _dispose_theme(self, *_args) -> None:
        theme = getattr(self, "_theme", None)
        if theme is not None:
            theme.dispose()

    # -------------------------------------------------------------- accent row

    def _build_accent_row(self) -> Gtk.Widget:
        row = Adw.PreferencesRow()
        row.set_activatable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title = Gtk.Label(label="Акцентный цвет", xalign=0.0)
        title.add_css_class("heading")
        title.set_hexpand(True)
        header.append(title)
        self._accent_hex = Gtk.Label(label="")
        self._accent_hex.add_css_class("accent-hex")
        self._accent_hex.set_valign(Gtk.Align.CENTER)
        header.append(self._accent_hex)
        box.append(header)

        self._accent_hint = Gtk.Label(label="", xalign=0.0)
        self._accent_hint.add_css_class("section-hint")
        self._accent_hint.set_wrap(True)
        box.append(self._accent_hint)

        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_homogeneous(True)
        flow.set_max_children_per_line(8)
        flow.set_min_children_per_line(4)
        flow.set_row_spacing(8)
        flow.set_column_spacing(8)
        flow.set_halign(Gtk.Align.START)
        flow.add_css_class("accent-flow")
        self._accent_swatches: list[tuple[str, Gtk.Button]] = []
        for name, hex_color in ACCENT_PRESETS:
            button = self._make_accent_swatch(hex_color)
            button.set_tooltip_text(name)
            button.connect(
                "clicked", lambda _b, c=hex_color: self._set_accent("preset", c)
            )
            flow.append(button)
            self._accent_swatches.append((hex_color, button))
        box.append(flow)

        if schemes_from_seed is not None:
            strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            strip.set_halign(Gtk.Align.START)
            self._accent_tones: list[tuple[str, Gtk.Box]] = []
            for role, tooltip in _TONE_ROLES:
                chip = Gtk.Box()
                chip.set_size_request(44, 22)
                chip.add_css_class("accent-tone")
                chip.set_tooltip_text(tooltip)
                provider = Gtk.CssProvider()
                chip.get_style_context().add_provider(
                    provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
                )
                chip._tone_provider = provider
                strip.append(chip)
                self._accent_tones.append((role, chip))
            box.append(strip)
            Adw.StyleManager.get_default().connect(
                "notify::dark", lambda *_: self._refresh_accent_tones()
            )

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.add_css_class("accent-actions")
        custom = Gtk.Button(label="Свой цвет")
        custom.set_icon_name("color-select-symbolic")
        custom.set_tooltip_text("Выбрать произвольный цвет")
        custom.connect("clicked", lambda *_: self._choose_custom_accent())
        actions.append(custom)
        self._accent_custom_button = custom

        wallpaper = Gtk.Button(label="Из обоев")
        wallpaper.set_icon_name("preferences-desktop-wallpaper-symbolic")
        wallpaper.set_tooltip_text("Собрать палитру из цвета обоев")
        wallpaper.connect("clicked", lambda *_: self._use_wallpaper_accent())
        actions.append(wallpaper)
        self._accent_wallpaper_button = wallpaper

        reset = Gtk.Button(label="Сбросить")
        reset.set_icon_name("edit-undo-symbolic")
        reset.set_tooltip_text("Вернуть синий акцент по умолчанию")
        reset.connect(
            "clicked", lambda *_: self._set_accent("preset", DEFAULT_ACCENT)
        )
        actions.append(reset)
        box.append(actions)

        row.set_child(box)
        GLib.idle_add(self._accent_row_ready)
        return row

    def _accent_row_ready(self) -> bool:
        if getattr(self, "_closing", False):
            return False
        self._refresh_accent_selection()
        if str(self.store.settings.get("accent_mode", "preset")) == "wallpaper":
            self._refresh_wallpaper_accent(silent=True)
        return False

    @staticmethod
    def _make_accent_swatch(hex_color: str) -> Gtk.Button:
        hex_color = normalize_hex(hex_color)
        fg = on_color(hex_color)
        button = Gtk.Button()
        button.add_css_class("accent-swatch")
        button.set_halign(Gtk.Align.CENTER)
        button.set_valign(Gtk.Align.CENTER)
        check = Gtk.Image.new_from_icon_name("object-select-symbolic")
        check.set_pixel_size(16)
        check.set_visible(False)
        button.set_child(check)
        provider = Gtk.CssProvider()
        provider.load_from_data(
            (
                "button.accent-swatch {"
                f" background-image: none; background-color: {hex_color}; color: {fg}; }}"
            ).encode("utf-8")
        )
        button.get_style_context().add_provider(
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )
        button._accent_check = check
        button._accent_provider = provider
        return button

    # ----------------------------------------------------------------- state

    def _refresh_accent_tones(self) -> None:
        tones = getattr(self, "_accent_tones", None)
        if not tones or schemes_from_seed is None:
            return
        try:
            light, dark = schemes_from_seed(self._theme.seed)
            palette = dark if Adw.StyleManager.get_default().get_dark() else light
            for role, chip in tones:
                color = palette.get(role, "#808080")
                chip._tone_provider.load_from_data(
                    (
                        "box.accent-tone { border-radius: 7px;"
                        f" background-color: {color};"
                        " box-shadow: inset 0 0 0 1px rgba(0,0,0,0.16); }"
                    ).encode("utf-8")
                )
        except Exception:
            pass

    def _refresh_accent_selection(self) -> None:
        mode = str(self.store.settings.get("accent_mode", "preset"))
        current = normalize_hex(self.store.settings.get("accent_color", DEFAULT_ACCENT))
        for hex_color, button in getattr(self, "_accent_swatches", []):
            selected = mode == "preset" and normalize_hex(hex_color) == current
            button._accent_check.set_visible(selected)
            if selected:
                button.add_css_class("accent-selected")
            else:
                button.remove_css_class("accent-selected")
        for widget, active in (
            (getattr(self, "_accent_custom_button", None), mode == "custom"),
            (getattr(self, "_accent_wallpaper_button", None), mode == "wallpaper"),
        ):
            if widget is None:
                continue
            if active:
                widget.add_css_class("accent-mode-active")
            else:
                widget.remove_css_class("accent-mode-active")
        if hasattr(self, "_accent_hex"):
            self._accent_hex.set_text(current)
        if hasattr(self, "_accent_hint"):
            self._accent_hint.set_text(
                f"{_MODE_LABELS.get(mode, 'Пресет')} · вся палитра приложения "
                "пересобирается из этого цвета"
            )
        self._refresh_accent_tones()

    def _set_accent(self, mode: str, color: str, *, notify: bool = True) -> None:
        color = normalize_hex(color)
        self.store.set_setting("accent_mode", mode)
        self.store.set_setting("accent_color", color)
        self._theme.set_seed(color)
        self._refresh_accent_selection()
        if notify:
            self._toast(f"Акцент обновлён: {color}")

    # ---------------------------------------------------------------- custom

    def _choose_custom_accent(self) -> None:
        current = Gdk.RGBA()
        current.parse(
            normalize_hex(self.store.settings.get("accent_color", DEFAULT_ACCENT))
        )
        if hasattr(Gtk, "ColorDialog"):
            dialog = Gtk.ColorDialog(with_alpha=False)
            dialog.choose_rgba(self, current, None, self._custom_accent_chosen)
        else:
            dialog = Gtk.ColorChooserDialog(title="Акцентный цвет", transient_for=self)
            dialog.set_rgba(current)
            dialog.connect("response", self._legacy_accent_response)
            dialog.show()

    @staticmethod
    def _rgba_to_hex(rgba) -> str:
        return "#%02X%02X%02X" % (
            round(rgba.red * 255),
            round(rgba.green * 255),
            round(rgba.blue * 255),
        )

    def _custom_accent_chosen(self, dialog, result) -> None:
        try:
            rgba = dialog.choose_rgba_finish(result)
        except GLib.Error:
            return
        self._set_accent("custom", self._rgba_to_hex(rgba))

    def _legacy_accent_response(self, dialog, response) -> None:
        if response == Gtk.ResponseType.OK:
            self._set_accent("custom", self._rgba_to_hex(dialog.get_rgba()))
        dialog.destroy()

    # ------------------------------------------------------------- wallpaper

    def _use_wallpaper_accent(self) -> None:
        self._refresh_wallpaper_accent(silent=False)

    def _refresh_wallpaper_accent(self, *, silent: bool) -> None:
        def worker() -> None:
            try:
                color = extract_wallpaper_accent()
            except Exception:
                color = None
            GLib.idle_add(self._wallpaper_accent_done, color, silent)

        try:
            self._fetch_pool.submit(worker)
        except (RuntimeError, AttributeError):
            try:
                color = extract_wallpaper_accent()
            except Exception:
                color = None
            self._wallpaper_accent_done(color, silent)

    def _wallpaper_accent_done(self, color: str | None, silent: bool) -> bool:
        if getattr(self, "_closing", False):
            return False
        if color is None:
            if not silent:
                self._toast("Не удалось прочитать обои — выбери цвет вручную")
            return False
        self._set_accent("wallpaper", color, notify=not silent)
        return False
