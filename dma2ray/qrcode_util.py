"""QR-коды для профилей.

Генерация картинки QR-кода со ссылкой профиля (чтобы отсканировать с телефона)
и чтение QR-кода из файла-изображения (импорт).

Зависимость qrcode опциональна: если не установлена — функции возвращают None
и приложение показывает подсказку.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

try:
    import qrcode

    QRCODE_AVAILABLE = True
except ImportError:  # pragma: no cover - зависимость опциональна
    QRCODE_AVAILABLE = False


def generate_qr_png(data: str) -> bytes | None:
    """Сгенерировать PNG-картинку QR-кода со строками data.

    Возвращает байты PNG или None, если библиотека qrcode не установлена.
    """
    if not QRCODE_AVAILABLE:
        return None
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def decode_qr_from_file(path: Path) -> str | None:
    """Прочитать QR-код из файла-изображения через zbarimg.

    Возвращает строку (ссылку) или None, если не удалось распознать.
    """
    try:
        result = subprocess.run(
            ["zbarimg", "--quiet", "--raw", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None
