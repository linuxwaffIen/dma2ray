#!/bin/bash
set -euo pipefail

BIN="dist/dma2ray.dist/dma2ray"
ARCH="${1:-amd64}"

case "$ARCH" in
    amd64)
        DEB_ARCH="amd64"
        PKG_ARCH="x86_64"
        APK_ARCH="x86_64"
        ;;
    arm64)
        DEB_ARCH="arm64"
        PKG_ARCH="aarch64"
        APK_ARCH="aarch64"
        ;;
    *)
        echo "Unknown arch: $ARCH"
        exit 1
        ;;
esac

STAGE="pkg_stage"
rm -rf "$STAGE"
mkdir -p "$STAGE/usr/usr/lib/dma2ray/app"
mkdir -p "$STAGE/usr/usr/bin"
mkdir -p "$STAGE/usr/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$STAGE/usr/usr/share/applications"

cp -a "$BIN" "$STAGE/usr/usr/lib/dma2ray/app/dma2ray"
chmod 755 "$STAGE/usr/usr/lib/dma2ray/app/dma2ray"
ln -s ../lib/dma2ray/app/dma2ray "$STAGE/usr/usr/bin/dma2ray"

cp -a data/io.github.dma2ray.Dma2ray.svg "$STAGE/usr/usr/share/icons/hicolor/scalable/apps/"
cp -a data/io.github.dma2ray.Dma2ray.desktop "$STAGE/usr/usr/share/applications/"
cp -a LICENSE README.md "$STAGE/usr/usr/lib/dma2ray/"

# Копируем все .so и вспомогательные файлы
cp -a dist/dma2ray.dist/helpers "$STAGE/usr/usr/lib/dma2ray/app/helpers"
cp -a dist/dma2ray.dist/girepository "$STAGE/usr/usr/lib/dma2ray/app/girepository"
cp -a dist/dma2ray.dist/*.so "$STAGE/usr/usr/lib/dma2ray/app/" 2>/dev/null || true
cp -a dist/dma2ray.dist/_*.so "$STAGE/usr/usr/lib/dma2ray/app/" 2>/dev/null || true
cp -a dist/dma2ray.dist/array.so dist/dma2ray.dist/zlib.so dist/dma2ray.dist/unicodedata.so \
    dist/dma2ray.dist/select.so dist/dma2ray.dist/pyexpat.so dist/dma2ray.dist/mmap.so \
    dist/dma2ray.dist/math.so dist/dma2ray.dist/grp.so dist/dma2ray.dist/binascii.so \
    dist/dma2ray.dist/libpython3.14.so.1.0 dist/dma2ray.dist/libexpat.so.1 \
    dist/dma2ray.dist/libuuid.so.1 dist/dma2ray.dist/libssl.so.3 dist/dma2ray.dist/liblzma.so.5 \
    dist/dma2ray.dist/libbrotlicommon.so.1 dist/dma2ray.dist/libzstd.so.1 \
    dist/dma2ray.dist/libbrotlidec.so.1 dist/dma2ray.dist/libbrotlienc.so.1 \
    dist/dma2ray.dist/libcrypto.so.3 dist/dma2ray.dist/libmpdec.so.4 \
    dist/dma2ray.dist/libffi.so.8 dist/dma2ray.dist/libbz2.so.1.0 \
    "$STAGE/usr/usr/lib/dma2ray/app/" 2>/dev/null || true

# --- DEB ---
DEB_STAGE="deb_stage"
rm -rf "$DEB_STAGE"
mkdir -p "$DEB_STAGE/DEBIAN"
cat > "$DEB_STAGE/DEBIAN/control" <<DEBCONTROL
Package: dma2ray
Version: 0.2.0-1
Section: net
Priority: optional
Architecture: $DEB_ARCH
Maintainer: Dma2ray contributors <linuxwaffIen@users.noreply.github.com>
Description: Dma2ray - VLESS client for Linux (GTK4/libadwaita, Xray-core)
 Homepage: https://github.com/linuxwaffIen/dma2ray
DEBCONTROL

# Копируем файлы из STAGING в DEB_STAGE
mkdir -p "$DEB_STAGE/usr/usr/lib/dma2ray/app"
mkdir -p "$DEB_STAGE/usr/usr/bin"
mkdir -p "$DEB_STAGE/usr/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$DEB_STAGE/usr/usr/share/applications"
cp -a "$STAGE/usr/usr/lib/dma2ray/app/dma2ray" "$DEB_STAGE/usr/usr/lib/dma2ray/app/dma2ray"
chmod 755 "$DEB_STAGE/usr/usr/lib/dma2ray/app/dma2ray"
ln -s ../lib/dma2ray/app/dma2ray "$DEB_STAGE/usr/usr/bin/dma2ray"
cp -a "$STAGE/usr/usr/share/icons/hicolor/scalable/apps/io.github.dma2ray.Dma2ray.svg" \
    "$DEB_STAGE/usr/usr/share/icons/hicolor/scalable/apps/"
cp -a "$STAGE/usr/usr/share/applications/io.github.dma2ray.Dma2ray.desktop" \
    "$DEB_STAGE/usr/usr/share/applications/"
cp -a "$STAGE/usr/usr/lib/dma2ray/LICENSE" "$DEB_STAGE/usr/usr/lib/dma2ray/LICENSE"
cp -a "$STAGE/usr/usr/lib/dma2ray/README.md" "$DEB_STAGE/usr/usr/lib/dma2ray/README.md"
cp -a "$STAGE/usr/usr/lib/dma2ray/app/helpers" "$DEB_STAGE/usr/usr/lib/dma2ray/app/helpers"
cp -a "$STAGE/usr/usr/lib/dma2ray/app/girepository" "$DEB_STAGE/usr/usr/lib/dma2ray/app/girepository"
cp -a "$STAGE/usr/usr/lib/dma2ray/app/"*.so "$DEB_STAGE/usr/usr/lib/dma2ray/app/" 2>/dev/null || true
cp -a "$STAGE/usr/usr/lib/dma2ray/app/"_*.so "$DEB_STAGE/usr/usr/lib/dma2ray/app/" 2>/dev/null || true

dpkg-deb --build "$DEB_STAGE" "dma2ray_0.2.0-1_${DEB_ARCH}.deb"
echo "Built: dma2ray_0.2.0-1_${DEB_ARCH}.deb"
ls -lh "dma2ray_0.2.0-1_${DEB_ARCH}.deb"

# --- ARCH ---
ARCH_STAGE="arch_stage"
rm -rf "$ARCH_STAGE"
mkdir -p "$ARCH_STAGE/usr/lib/dma2ray/app"
mkdir -p "$ARCH_STAGE/usr/bin"
mkdir -p "$ARCH_STAGE/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$ARCH_STAGE/usr/share/applications"

cp -a "$BIN" "$ARCH_STAGE/usr/lib/dma2ray/app/dma2ray"
chmod 755 "$ARCH_STAGE/usr/lib/dma2ray/app/dma2ray"
ln -s ../lib/dma2ray/app/dma2ray "$ARCH_STAGE/usr/bin/dma2ray"

cp -a data/io.github.dma2ray.Dma2ray.svg "$ARCH_STAGE/usr/share/icons/hicolor/scalable/apps/"
cp -a data/io.github.dma2ray.Dma2ray.desktop "$ARCH_STAGE/usr/share/applications/"
cp -a LICENSE README.md "$ARCH_STAGE/usr/lib/dma2ray/"
cp -a dist/dma2ray.dist/helpers "$ARCH_STAGE/usr/lib/dma2ray/app/helpers"
cp -a dist/dma2ray.dist/girepository "$ARCH_STAGE/usr/lib/dma2ray/app/girepository"
cp -a dist/dma2ray.dist/*.so "$ARCH_STAGE/usr/lib/dma2ray/app/" 2>/dev/null || true
cp -a dist/dma2ray.dist/_*.so "$ARCH_STAGE/usr/lib/dma2ray/app/" 2>/dev/null || true
cp -a dist/dma2ray.dist/array.so dist/dma2ray.dist/zlib.so dist/dma2ray.dist/unicodedata.so \
    dist/dma2ray.dist/select.so dist/dma2ray.dist/pyexpat.so dist/dma2ray.dist/mmap.so \
    dist/dma2ray.dist/math.so dist/dma2ray.dist/grp.so dist/dma2ray.dist/binascii.so \
    dist/dma2ray.dist/libpython3.14.so.1.0 dist/dma2ray.dist/libexpat.so.1 \
    dist/dma2ray.dist/libuuid.so.1 dist/dma2ray.dist/libssl.so.3 dist/dma2ray.dist/liblzma.so.5 \
    dist/dma2ray.dist/libbrotlicommon.so.1 dist/dma2ray.dist/libzstd.so.1 \
    dist/dma2ray.dist/libbrotlidec.so.1 dist/dma2ray.dist/libbrotlienc.so.1 \
    dist/dma2ray.dist/libcrypto.so.3 dist/dma2ray.dist/libmpdec.so.4 \
    dist/dma2ray.dist/libffi.so.8 dist/dma2ray.dist/libbz2.so.1.0 \
    "$ARCH_STAGE/usr/lib/dma2ray/app/" 2>/dev/null || true

cat > "$ARCH_STAGE/.PKGINFO" <<PKGINFO
pkgname = dma2ray
pkgver = 0.2.0-1
pkgdesc = Dma2ray VLESS client (GTK4/libadwaita, Xray-core)
url = https://github.com/linuxwaffIen/dma2ray
arch = $PKG_ARCH
license = GPL-3.0-only
size = 14484153
PKGINFO

bsdtar -cf - -C "$ARCH_STAGE" usr .PKGINFO | zstd -19 -o "dma2ray-0.2.0-1-${PKG_ARCH}.pkg.tar.zst"
echo "Built: dma2ray-0.2.0-1-${PKG_ARCH}.pkg.tar.zst"
ls -lh "dma2ray-0.2.0-1-${PKG_ARCH}.pkg.tar.zst"

# --- APK ---
APK_STAGE="apk_stage"
rm -rf "$APK_STAGE"
mkdir -p "$APK_STAGE/usr/usr/lib/dma2ray/app"
mkdir -p "$APK_STAGE/usr/usr/bin"
mkdir -p "$APK_STAGE/usr/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$APK_STAGE/usr/usr/share/applications"

cp -a "$BIN" "$APK_STAGE/usr/usr/lib/dma2ray/app/dma2ray"
chmod 755 "$APK_STAGE/usr/usr/lib/dma2ray/app/dma2ray"
ln -s ../lib/dma2ray/app/dma2ray "$APK_STAGE/usr/usr/bin/dma2ray"

cp -a data/io.github.dma2ray.Dma2ray.svg "$APK_STAGE/usr/usr/share/icons/hicolor/scalable/apps/"
cp -a data/io.github.dma2ray.Dma2ray.desktop "$APK_STAGE/usr/usr/share/applications/"
cp -a LICENSE README.md "$APK_STAGE/usr/usr/lib/dma2ray/"
cp -a dist/dma2ray.dist/helpers "$APK_STAGE/usr/usr/lib/dma2ray/app/helpers"
cp -a dist/dma2ray.dist/girepository "$APK_STAGE/usr/usr/lib/dma2ray/app/girepository"
cp -a dist/dma2ray.dist/*.so "$APK_STAGE/usr/usr/lib/dma2ray/app/" 2>/dev/null || true
cp -a dist/dma2ray.dist/_*.so "$APK_STAGE/usr/usr/lib/dma2ray/app/" 2>/dev/null || true
cp -a dist/dma2ray.dist/array.so dist/dma2ray.dist/zlib.so dist/dma2ray.dist/unicodedata.so \
    dist/dma2ray.dist/select.so dist/dma2ray.dist/pyexpat.so dist/dma2ray.dist/mmap.so \
    dist/dma2ray.dist/math.so dist/dma2ray.dist/grp.so dist/dma2ray.dist/binascii.so \
    dist/dma2ray.dist/libpython3.14.so.1.0 dist/dma2ray.dist/libexpat.so.1 \
    dist/dma2ray.dist/libuuid.so.1 dist/dma2ray.dist/libssl.so.3 dist/dma2ray.dist/liblzma.so.5 \
    dist/dma2ray.dist/libbrotlicommon.so.1 dist/dma2ray.dist/libzstd.so.1 \
    dist/dma2ray.dist/libbrotlidec.so.1 dist/dma2ray.dist/libbrotlienc.so.1 \
    dist/dma2ray.dist/libcrypto.so.3 dist/dma2ray.dist/libmpdec.so.4 \
    dist/dma2ray.dist/libffi.so.8 dist/dma2ray.dist/libbz2.so.1.0 \
    "$APK_STAGE/usr/usr/lib/dma2ray/app/" 2>/dev/null || true

SIZE=$(stat -c%s "$APK_STAGE/usr/usr/lib/dma2ray/app/dma2ray")
cat > "$APK_STAGE/.PKGINFO" <<PKGINFO
pkgname = dma2ray
pkgver = 0.2.0-r1
pkgdesc = Dma2ray VLESS client (GTK4/libadwaita, Xray-core)
url = https://github.com/linuxwaffIen/dma2ray
arch = $APK_ARCH
license = GPL-3.0-only
size = $SIZE
PKGINFO

tar --format=ustar -czf "$APK_STAGE/pkg.tar" -C "$APK_STAGE" .PKGINFO usr
gzip -9 -c "$APK_STAGE/pkg.tar" > "dma2ray-0.2.0-r1-${APK_ARCH}.apk"
rm -f "$APK_STAGE/pkg.tar"
echo "Built: dma2ray-0.2.0-r1-${APK_ARCH}.apk"
ls -lh "dma2ray-0.2.0-r1-${APK_ARCH}.apk"