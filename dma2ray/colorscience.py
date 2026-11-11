"""Тональные палитры Material 3 из одного seed-цвета.

Тон = L* (CIELAB, D65) — ровно то, что Material называет tone. Цвет собирается
в CIELCh; если он не влезает в sRGB, хрома уменьшается бисекцией до границы
гамута. Яркость (Y) зависит только от тона, поэтому контраст пар on_*/…
гарантирован конструкцией, а не подбором.

Зависимостей нет, только math.
"""

from __future__ import annotations

import math
from functools import lru_cache

_WHITE = (0.95047, 1.00000, 1.08883)

_RGB_TO_XYZ = (
    (0.4124564, 0.3575761, 0.1804375),
    (0.2126729, 0.7151522, 0.0721750),
    (0.0193339, 0.1191920, 0.9503041),
)
_XYZ_TO_RGB = (
    (3.2404542, -1.5371385, -0.4985314),
    (-0.9692660, 1.8760108, 0.0415560),
    (0.0556434, -0.2040259, 1.0572252),
)

_EPS = 216.0 / 24389.0
_KAPPA = 24389.0 / 27.0
_DELTA = 6.0 / 29.0


def _mat(m, v):
    return (
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
    )


def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_gamma(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1.0 / 2.4) - 0.055


def _f(t: float) -> float:
    return t ** (1.0 / 3.0) if t > _EPS else (_KAPPA * t + 16.0) / 116.0


def _finv(t: float) -> float:
    return t * t * t if t > _DELTA else (116.0 * t - 16.0) / _KAPPA


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def rgb_to_lch(r: int, g: int, b: int) -> tuple[float, float, float]:
    lin = (_to_linear(r / 255.0), _to_linear(g / 255.0), _to_linear(b / 255.0))
    x, y, z = _mat(_RGB_TO_XYZ, lin)
    fx, fy, fz = _f(x / _WHITE[0]), _f(y / _WHITE[1]), _f(z / _WHITE[2])
    lightness = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    bb = 200.0 * (fy - fz)
    return lightness, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360.0


def _lch_to_linear(lightness: float, chroma: float, hue: float):
    hr = math.radians(hue)
    a = chroma * math.cos(hr)
    bb = chroma * math.sin(hr)
    fy = (lightness + 16.0) / 116.0
    fx = fy + a / 500.0
    fz = fy - bb / 200.0
    xyz = (_WHITE[0] * _finv(fx), _WHITE[1] * _finv(fy), _WHITE[2] * _finv(fz))
    return _mat(_XYZ_TO_RGB, xyz)


def _in_gamut(lin) -> bool:
    return all(-1e-7 <= v <= 1.0 + 1e-7 for v in lin)


def _encode(lin) -> str:
    out = []
    for v in lin:
        v = min(1.0, max(0.0, v))
        out.append(int(round(_to_gamma(v) * 255.0)))
    return "#%02X%02X%02X" % (out[0], out[1], out[2])


@lru_cache(maxsize=16384)
def tone_to_hex(hue: float, chroma: float, tone: float) -> str:
    lightness = min(100.0, max(0.0, tone))
    if lightness <= 0.0:
        return "#000000"
    if lightness >= 100.0:
        return "#FFFFFF"
    if chroma <= 0.01:
        return _encode(_lch_to_linear(lightness, 0.0, 0.0))
    lin = _lch_to_linear(lightness, chroma, hue)
    if _in_gamut(lin):
        return _encode(lin)
    lo, hi = 0.0, chroma
    for _ in range(24):
        mid = (lo + hi) * 0.5
        if _in_gamut(_lch_to_linear(lightness, mid, hue)):
            lo = mid
        else:
            hi = mid
    return _encode(_lch_to_linear(lightness, lo, hue))


def relative_luminance(value: str) -> float:
    r, g, b = hex_to_rgb(value)
    lin = (_to_linear(r / 255.0), _to_linear(g / 255.0), _to_linear(b / 255.0))
    return 0.2126729 * lin[0] + 0.7151522 * lin[1] + 0.0721750 * lin[2]


def contrast_ratio(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def best_on_color(background: str) -> str:
    return max(("#FFFFFF", "#101014"), key=lambda c: contrast_ratio(background, c))


class TonalPalette:
    __slots__ = ("hue", "chroma")

    def __init__(self, hue: float, chroma: float) -> None:
        self.hue = float(hue) % 360.0
        self.chroma = max(0.0, float(chroma))

    def tone(self, value: float) -> str:
        return tone_to_hex(round(self.hue, 3), round(self.chroma, 3), float(value))

    @classmethod
    def from_seed(cls, seed_hex: str, min_chroma: float = 48.0) -> "TonalPalette":
        _, chroma, hue = rgb_to_lch(*hex_to_rgb(seed_hex))
        return cls(hue, chroma if chroma < 12.0 else max(chroma, min_chroma))


def schemes_from_seed(seed_hex: str) -> tuple[dict, dict]:
    primary = TonalPalette.from_seed(seed_hex)
    secondary = TonalPalette(primary.hue, 16.0)
    tertiary = TonalPalette(primary.hue + 60.0, 26.0)
    neutral = TonalPalette(primary.hue, 4.0)
    variant = TonalPalette(primary.hue, 8.0)
    error = TonalPalette(33.0, 82.0)
    success = TonalPalette(145.0, 58.0)
    warning = TonalPalette(78.0, 78.0)

    def build(dark: bool) -> dict:
        def pick(pal: TonalPalette, light: float, deep: float) -> str:
            return pal.tone(deep if dark else light)

        return {
            "primary": pick(primary, 40, 80),
            "on_primary": pick(primary, 100, 20),
            "primary_container": pick(primary, 90, 30),
            "on_primary_container": pick(primary, 10, 90),
            "secondary": pick(secondary, 40, 80),
            "on_secondary": pick(secondary, 100, 20),
            "secondary_container": pick(secondary, 90, 30),
            "on_secondary_container": pick(secondary, 10, 90),
            "tertiary": pick(tertiary, 40, 80),
            "tertiary_container": pick(tertiary, 90, 30),
            "on_tertiary_container": pick(tertiary, 10, 90),
            "error": pick(error, 40, 80),
            "on_error": pick(error, 100, 20),
            "error_container": pick(error, 90, 30),
            "on_error_container": pick(error, 10, 90),
            "success": pick(success, 40, 80),
            "on_success": pick(success, 100, 20),
            "success_container": pick(success, 90, 30),
            "on_success_container": pick(success, 10, 90),
            "warning": pick(warning, 40, 80),
            "on_warning": pick(warning, 100, 20),
            "warning_container": pick(warning, 90, 30),
            "on_warning_container": pick(warning, 10, 90),
            "surface": pick(neutral, 98, 6),
            "surface_container_lowest": pick(neutral, 100, 4),
            "surface_container_low": pick(neutral, 96, 10),
            "surface_container": pick(neutral, 94, 12),
            "surface_container_high": pick(neutral, 92, 17),
            "surface_container_highest": pick(neutral, 90, 22),
            "on_surface": pick(neutral, 10, 90),
            "on_surface_variant": pick(variant, 30, 80),
            "outline": pick(variant, 50, 60),
            "outline_variant": pick(variant, 80, 30),
            "inverse_surface": pick(neutral, 20, 90),
            "inverse_on_surface": pick(neutral, 95, 20),
            "card_bg": pick(neutral, 100, 10),
            "shadow": "#000000",
        }

    return build(False), build(True)
