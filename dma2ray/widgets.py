"""Material 3 ripple: волна из точки нажатия, обрезанная по форме кнопки."""

from __future__ import annotations

import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk

_GROW_MS = 420.0
_FADE_MS = 260.0
_ALPHA = 0.16
_MAX_RIPPLES = 4


def _rect(x: float, y: float, w: float, h: float) -> Graphene.Rect:
    r = Graphene.Rect()
    r.init(x, y, w, h)
    return r


def _rounded(bounds: Graphene.Rect, radius: float) -> Gsk.RoundedRect:
    rr = Gsk.RoundedRect()
    rr.init_from_rect(bounds, radius)
    return rr


class RippleButton(Gtk.Button):
    __gtype_name__ = "DmaRippleButton"

    def __init__(self, *, corner_radius: float = 18.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self._corner = float(corner_radius)
        self._ripples: list[dict] = []
        self._tick_id = 0

        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("pressed", self._on_pressed)
        click.connect("released", self._on_released)
        click.connect("cancel", self._on_released)
        self.add_controller(click)

        self.connect("activate", self._on_activate)
        self.connect("unrealize", self._on_unrealize)

    # ---------------------------------------------------------- input

    def _spawn(self, x: float, y: float, released: bool) -> None:
        w, h = self.get_width(), self.get_height()
        if w <= 0 or h <= 0:
            return
        reach = max(math.hypot(px - x, py - y) for px in (0, w) for py in (0, h))
        now = GLib.get_monotonic_time()
        self._ripples.append(
            {"x": x, "y": y, "reach": reach, "t0": now, "t_rel": now if released else 0}
        )
        del self._ripples[:-_MAX_RIPPLES]
        self._ensure_tick()

    def _on_pressed(self, _gesture, _n_press, x, y) -> None:
        if self.get_sensitive():
            self._spawn(float(x), float(y), released=False)

    def _on_released(self, *_args) -> None:
        now = GLib.get_monotonic_time()
        for ripple in self._ripples:
            if not ripple["t_rel"]:
                ripple["t_rel"] = now
        self._ensure_tick()

    def _on_activate(self, *_args) -> None:
        if not self._ripples:
            self._spawn(self.get_width() / 2.0, self.get_height() / 2.0, released=True)

    def _on_unrealize(self, *_args) -> None:
        if self._tick_id:
            self.remove_tick_callback(self._tick_id)
            self._tick_id = 0
        self._ripples.clear()

    # ------------------------------------------------------- animation

    def _ensure_tick(self) -> None:
        if not self._tick_id:
            self._tick_id = self.add_tick_callback(self._on_tick)
        self.queue_draw()

    def _on_tick(self, _widget, frame_clock) -> bool:
        now = frame_clock.get_frame_time()
        alive = []
        for ripple in self._ripples:
            if ripple["t_rel"] and (now - ripple["t_rel"]) / 1000.0 >= _FADE_MS:
                continue
            if not ripple["t_rel"] and (now - ripple["t0"]) / 1000.0 >= 8000.0:
                continue
            alive.append(ripple)
        self._ripples = alive
        self.queue_draw()
        if self._ripples:
            return True
        self._tick_id = 0
        return False

    # -------------------------------------------------------- painting

    def do_snapshot(self, snapshot) -> None:
        Gtk.Button.do_snapshot(self, snapshot)
        if not self._ripples:
            return
        w, h = float(self.get_width()), float(self.get_height())
        if w <= 0.0 or h <= 0.0:
            return

        fg = self.get_color()
        now = GLib.get_monotonic_time()
        snapshot.push_rounded_clip(_rounded(_rect(0.0, 0.0, w, h), self._corner))
        for ripple in self._ripples:
            p = min(1.0, ((now - ripple["t0"]) / 1000.0) / _GROW_MS)
            eased = 1.0 - (1.0 - p) ** 3
            radius = ripple["reach"] * eased
            alpha = _ALPHA * min(1.0, p * 2.5)
            if ripple["t_rel"]:
                fade = min(1.0, ((now - ripple["t_rel"]) / 1000.0) / _FADE_MS)
                alpha *= 1.0 - fade
            if radius <= 0.5 or alpha <= 0.002:
                continue
            bounds = _rect(
                ripple["x"] - radius, ripple["y"] - radius, radius * 2.0, radius * 2.0
            )
            color = Gdk.RGBA()
            color.red, color.green, color.blue, color.alpha = (
                fg.red,
                fg.green,
                fg.blue,
                alpha,
            )
            snapshot.push_rounded_clip(_rounded(bounds, radius))
            snapshot.append_color(color, bounds)
            snapshot.pop()
        snapshot.pop()
