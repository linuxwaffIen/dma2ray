#!/usr/bin/env python3
"""Проверка генератора палитр Material 3. Запуск: python3 check_theme.py"""

from __future__ import annotations

import sys

from dma2ray.accent import ACCENT_PRESETS
from dma2ray.colorscience import (
    TonalPalette,
    contrast_ratio,
    hex_to_rgb,
    relative_luminance,
    rgb_to_lch,
    schemes_from_seed,
)

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  ok   " if ok else " FAIL  ") + name + (f"   {detail}" if detail else ""))
    if not ok:
        fails.append(name)


print("Нейтральная шкала (тон = L*):")
neutral = TonalPalette(0.0, 0.0)
check("tone 0 -> #000000", neutral.tone(0) == "#000000", neutral.tone(0))
check("tone 100 -> #FFFFFF", neutral.tone(100) == "#FFFFFF", neutral.tone(100))
check("tone 40 -> #5E5E5E", neutral.tone(40) == "#5E5E5E", neutral.tone(40))
check("tone 50 -> #777777", neutral.tone(50) == "#777777", neutral.tone(50))

tones = (0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98, 100)
lum = [relative_luminance(neutral.tone(t)) for t in tones]
check("яркость монотонно растёт", all(b > a for a, b in zip(lum, lum[1:])))

for name, seed in ACCENT_PRESETS:
    light, dark = schemes_from_seed(seed)
    print(
        f"\n{name} {seed}: primary {light['primary']}/{dark['primary']}"
        f"  surface {light['surface']}/{dark['surface']}"
        f"  text {light['on_surface']}/{dark['on_surface']}"
    )
    for label, p in (("light", light), ("dark", dark)):
        ratio = contrast_ratio(p["on_surface"], p["surface"])
        check(f"{name} {label}: текст >= 7", ratio >= 7.0, f"{ratio:.2f}")
        ratio = contrast_ratio(p["on_primary"], p["primary"])
        check(f"{name} {label}: on_primary >= 4.5", ratio >= 4.5, f"{ratio:.2f}")
        ratio = contrast_ratio(p["on_primary_container"], p["primary_container"])
        check(f"{name} {label}: контейнер >= 4.5", ratio >= 4.5, f"{ratio:.2f}")
        ratio = contrast_ratio(p["on_surface_variant"], p["card_bg"])
        check(f"{name} {label}: подсказка >= 4.5", ratio >= 4.5, f"{ratio:.2f}")
        ratio = contrast_ratio(p["on_error"], p["error"])
        check(f"{name} {label}: error >= 4.5", ratio >= 4.5, f"{ratio:.2f}")
        check(f"{name} {label}: карточка != фон", p["card_bg"] != p["surface"])
        floor = 0.5 if label == "light" else 0.002
        check(
            f"{name} {label}: фон не чёрный",
            relative_luminance(p["surface"]) > floor,
            f"Y={relative_luminance(p['surface']):.4f}",
        )

light, _ = schemes_from_seed("#2B5CE6")
chroma = rgb_to_lch(*hex_to_rgb(light["primary"]))[1]
check("синий seed остаётся цветным", chroma > 25.0, f"C={chroma:.1f}")

print()
if fails:
    print(f"{len(fails)} ПРОВЕРОК УПАЛО")
    sys.exit(1)
print("все проверки пройдены")
