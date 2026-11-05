#!/usr/bin/env bash
# Установщик Dma2ray.
#
# Примеры:
#   ./install.sh                 # в ~/.local
#   ./install.sh --system        # в /usr (нужен root)
#   ./install.sh --uninstall     # удалить пользовательскую установку
#   ./install.sh --uninstall --purge  # удалить также профили и кэш
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ID="io.github.dma2ray.Dma2ray"
APP_NAME="dma2ray"
MODE="user"
PREFIX="${PREFIX:-$HOME/.local}"
ACTION="install"
PURGE=0

usage() {
    cat <<'EOF'
Использование: ./install.sh [параметры]

  --system        установить в /usr (требуется root/sudo)
  --prefix DIR    префикс пользовательской установки (по умолчанию ~/.local)
  --uninstall     удалить приложение
  --purge         вместе с --uninstall удалить профили, кэш и автозапуск
  -h, --help      показать эту справку

Без --system файлы ставятся в ~/.local:
  ~/.local/lib/dma2ray        код: бинарник (app/), исходники, данные
  ~/.local/bin/dma2ray        симлинк на бинарник
  ~/.local/share/applications   ярлык
  ~/.local/share/icons          иконка
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --system)
            MODE="system"
            PREFIX="/usr"
            shift
            ;;
        --prefix)
            [[ $# -ge 2 ]] || { echo "Ошибка: --prefix требует каталог" >&2; exit 2; }
            PREFIX="$2"
            shift 2
            ;;
        --prefix=*)
            PREFIX="${1#*=}"
            shift
            ;;
        --uninstall)
            ACTION="uninstall"
            shift
            ;;
        --purge)
            PURGE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Неизвестный параметр: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ "$MODE" == "system" && "$PREFIX" != "/usr" ]]; then
    echo "Ошибка: --system всегда использует /usr" >&2
    exit 2
fi
if [[ "$MODE" == "system" && $EUID -ne 0 ]]; then
    echo "Для системной установки нужен root:" >&2
    echo "  sudo ./install.sh --system" >&2
    exit 1
fi

APP_DIR="$PREFIX/lib/$APP_NAME"
BIN="$PREFIX/bin/$APP_NAME"
DESKTOP_DIR="$PREFIX/share/applications"
ICON_DIR="$PREFIX/share/icons/hicolor/scalable/apps"
DESKTOP="$DESKTOP_DIR/$APP_ID.desktop"
ICON="$ICON_DIR/$APP_ID.svg"

update_caches() {
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" >/dev/null 2>&1 || true
    fi
}

register_scheme() {
    command -v xdg-mime >/dev/null 2>&1 || return 0
    if [[ "$MODE" == "user" ]]; then
        xdg-mime default "$APP_ID.desktop" x-scheme-handler/vless >/dev/null 2>&1 || true
    elif [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]] && command -v sudo >/dev/null 2>&1; then
        sudo -u "$SUDO_USER" xdg-mime default "$APP_ID.desktop" x-scheme-handler/vless \
            >/dev/null 2>&1 || true
    fi
}

uninstall() {
    rm -f "$BIN" "$DESKTOP" "$ICON"
    rm -rf "$APP_DIR"
    update_caches
    echo "Удалено: $APP_DIR, $BIN"
    if [[ $PURGE -eq 1 ]]; then
        if [[ "$MODE" == "system" ]]; then
            echo "Профили пользователей не удаляются при системной установке." >&2
        else
            rm -rf \
                "${XDG_CONFIG_HOME:-$HOME/.config}/$APP_NAME" \
                "${XDG_DATA_HOME:-$HOME/.local/share}/$APP_NAME" \
                "${XDG_CACHE_HOME:-$HOME/.cache}/$APP_NAME" \
                "${XDG_STATE_HOME:-$HOME/.local/state}/$APP_NAME"
            rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/$APP_NAME.desktop"
            echo "Удалены профили, кэш и автозапуск."
        fi
    fi
    echo "Готово."
}

install_app() {
    local bin_src="$ROOT/dist/dma2ray.dist/dma2ray"
    if [[ ! -x "$bin_src" ]]; then
        echo "Ошибка: бинарник не собран." >&2
        echo "Скомпилируйте исходники: ./build.sh" >&2
        echo "  (результат: dist/dma2ray.dist/dma2ray)" >&2
        exit 1
    fi
    for source in "$bin_src" "$ROOT/dma2ray" "$ROOT/data/$APP_ID.desktop" "$ROOT/data/$APP_ID.svg"; do
        [[ -e "$source" ]] || { echo "Не найден файл: $source" >&2; exit 1; }
    done

    install -d "$APP_DIR" "$PREFIX/bin" "$DESKTOP_DIR" "$ICON_DIR"
    rm -rf "$APP_DIR/dma2ray" "$APP_DIR/data" "$APP_DIR/app" "$APP_DIR/bin"
    cp -a "$ROOT/dma2ray" "$APP_DIR/"
    cp -a "$ROOT/data" "$APP_DIR/"
    # Скомпилированный бинарник с библиотеками, helper-скриптами и данными.
    cp -a "$ROOT/dist/dma2ray.dist" "$APP_DIR/app"
    cp -f "$ROOT/LICENSE" "$APP_DIR/LICENSE" 2>/dev/null || true
    cp -f "$ROOT/README.md" "$APP_DIR/README.md" 2>/dev/null || true
    find "$APP_DIR" -type d -name __pycache__ -prune -exec rm -rf {} +
    find "$APP_DIR" -type f -name '*.pyc' -delete

    # /prefix/bin/dma2ray — симлинк на бинарник (RPATH $ORIGIN переживает
    # симлинк, библиотеки ищутся рядом с настоящим файлом).
    ln -sfn "$APP_DIR/app/dma2ray" "$BIN"
    install -m 0644 "$ROOT/data/$APP_ID.svg" "$ICON"

    sed "s|^Exec=dma2ray$|Exec=$BIN|" \
        "$ROOT/data/$APP_ID.desktop" > "$DESKTOP"
    chmod 0644 "$DESKTOP"
    update_caches
    register_scheme

    echo "Dma2ray установлен:"
    echo "  приложение: $APP_DIR"
    echo "  бинарник:   $BIN -> $APP_DIR/app/dma2ray"
    echo "  ярлык:      $DESKTOP"
    if [[ "$MODE" == "user" && ":$PATH:" != *":$PREFIX/bin:"* ]]; then
        echo
        echo "Внимание: $PREFIX/bin отсутствует в PATH."
        echo "Добавьте его в ~/.profile или запускайте приложение по полному пути."
    fi
    echo
    echo "Ядро Xray можно скачать в «Настройках → Ядро → Скачать»"
}

if [[ "$ACTION" == "uninstall" ]]; then
    uninstall
else
    install_app
fi
