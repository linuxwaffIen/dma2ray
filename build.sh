#!/usr/bin/env bash
# Компиляция Dma2ray в единый бинарник (Nuitka, standalone-режим).
#
# Результат: dist/dma2ray.dist/dma2ray — самодостаточный ELF-бинарник
# (внутри каталога лежат библиотеки, helper-скрипты и данные).
#
# Запуск: ./build.sh
# Если Nuitka уже установлен системно (Arch: пакет AUR «nuitka», pacman:
# python-nuitka) — сборка идёт без сети. Иначе Nuitka и patchelf ставятся
# pip'ом в .build/venv (при первой сборке нужен интернет).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="$ROOT/.build/venv"

ensure_venv() {
    if [ ! -x "$VENV/bin/python" ]; then
        # --without-pip — запасной путь, если ensurepip недоступен
        # (в venv всё равно виден системный site-packages).
        python3 -m venv --system-site-packages "$VENV" \
            || python3 -m venv --system-site-packages --without-pip "$VENV"
    fi
}

# -m pip работает даже если в venv не создался собственный pip
# (--system-site-packages подхватывает системный python-pip).
pip_install() {
    ensure_venv
    "$VENV/bin/python" -m pip install --quiet "$@" || true
}

echo "1/4: окружение сборки..."
if python3 -c "import nuitka" >/dev/null 2>&1; then
    # Системный Nuitka (AUR «nuitka») — собираем сразу, без venv и сети.
    PY="python3"
    echo "     использую системный nuitka ($(python3 -c 'import nuitka, importlib.metadata as m; print(m.version(\"nuitka\"))' 2>/dev/null || echo '?'))"
else
    ensure_venv
    if ! "$VENV/bin/python" -c "import nuitka" >/dev/null 2>&1; then
        echo "     ставлю nuitka через pip..."
        pip_install nuitka
    fi
    if ! "$VENV/bin/python" -c "import nuitka" >/dev/null 2>&1; then
        echo "Ошибка: не удалось установить nuitka (нужен интернет," >&2
        "либо установите его: pacman -S nuitka (AUR) / pip install nuitka)" >&2
        exit 1
    fi
    PY="$VENV/bin/python"
fi

# Nuitka ищет patchelf и scons в PATH: сначала свой (venv), затем системный
# (pacman -S patchelf).
[ -d "$VENV/bin" ] && export PATH="$VENV/bin:$PATH"
if ! command -v patchelf >/dev/null 2>&1; then
    echo "     ставлю patchelf через pip (нужен для standalone-режима)..."
    pip_install patchelf
fi
if ! command -v patchelf >/dev/null 2>&1; then
    echo "Ошибка: patchelf не найден (pip install patchelf" >&2
    "либо pacman -S patchelf)" >&2
    exit 1
fi

# Ограничение параллелизма/памяти для слабых машин (например QEMU-гость):
#   DMA2RAY_JOBS=2 DMA2RAY_LOW_MEMORY=1 ./build.sh
NA_OPTS=()
if [ -n "${DMA2RAY_JOBS:-}" ]; then
    NA_OPTS+=(--jobs="$DMA2RAY_JOBS")
fi
if [ "${DMA2RAY_LOW_MEMORY:-0}" = "1" ]; then
    NA_OPTS+=(--low-memory)
fi

echo "2/4: точка входа (.build/entry.py)..."
mkdir -p "$ROOT/.build"
cat > "$ROOT/.build/entry.py" <<'EOF'
# Точка входа для сборки: run.py удалён, приложение компилируется в бинарник.
import sys

from dma2ray.app import main

raise SystemExit(main())
EOF

echo "3/4: компиляция (1-3 минуты)..."
rm -rf "$ROOT/dist"
"$PY" -m nuitka \
    --standalone \
    --output-dir="$ROOT/dist" \
    --output-filename=dma2ray \
    --include-package=gi \
    --assume-yes-for-downloads \
    ${NA_OPTS[@]+"${NA_OPTS[@]}"} \
    "$ROOT/.build/entry.py"
mv "$ROOT/dist/entry.dist" "$ROOT/dist/dma2ray.dist"

echo "4/4: helper-скрипты и данные рядом с бинарником..."
# __file__ скомпилированных модулей указывает внутрь dist-каталога,
# поэтому privileged.py/tray_helper.py и data/ кладутся туда же.
mkdir -p "$ROOT/dist/dma2ray.dist/helpers"
cp -a "$ROOT/dma2ray/privileged.py" "$ROOT/dma2ray/tray_helper.py" \
      "$ROOT/dist/dma2ray.dist/helpers/"
cp -a "$ROOT/data" "$ROOT/dist/dma2ray.dist/"
cp -a "$ROOT/LICENSE" "$ROOT/README.md" "$ROOT/dist/dma2ray.dist/" 2>/dev/null || true

echo
echo "Готово: dist/dma2ray.dist/dma2ray"
ls -lh "$ROOT/dist/dma2ray.dist/dma2ray"
"$ROOT/dist/dma2ray.dist/dma2ray" --version
