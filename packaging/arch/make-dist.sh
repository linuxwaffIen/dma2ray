#!/usr/bin/env bash
# Создаёт исходный тарбол dma2ray-<версия>.tar.gz рядом с PKGBUILD.
# Запуск: ./make-dist.sh  (затем makepkg -si).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
VER="$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); from dma2ray.paths import VERSION; print(VERSION)")"
OUT="$HERE/dma2ray-$VER.tar.gz"

# Тарбол — только исходники: ядро Xray скачивается приложением при запуске,
# бинарник компилируется при сборке (./build.sh).
# Не входят: .build/ dist/ кэш и сам packaging/.
tar -czf "$OUT" -C "$ROOT" \
    --transform "s|^|dma2ray-$VER/|" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    build.sh dma2ray data install.sh LICENSE README.md tests

echo "Создан: $OUT"
ls -lh "$OUT"
sha256sum "$OUT"
