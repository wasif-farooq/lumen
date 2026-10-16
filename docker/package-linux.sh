#!/bin/sh
# Build Lumen's Linux packages: a .deb and an AppImage, written to /out.
# Runs in the flutter-linux image with the repo mounted read-only at /src
# (docker compose --profile build run --rm package). Both packages hold:
#   app/                 the Flutter desktop app
#   server/python/       a self-contained Python 3.12 with lumen and its dependencies
#   lumen-launcher       starts the bundled server, then the app (AppRun in the AppImage)
set -eu

VERSION="${LUMEN_VERSION:-$(sed -n 's/^version = "\(.*\)"/\1/p' /src/pyproject.toml | head -1)}"
VERSION="${VERSION#v}"
OUT=/out
ROOT=/tmp/lumen          # becomes /opt/lumen in the .deb, and the AppDir
export UV_CACHE_DIR="${UV_CACHE_DIR:-/home/ubuntu/.cache/uv}"
echo "== Lumen $VERSION"

rm -rf "$ROOT" /tmp/srccopy && mkdir -p "$ROOT/server" /tmp/srccopy

# --- 1. Flutter app (built from a copy, so the host's build folders are never touched) ---
tar -C /src/app --exclude=./build --exclude=./dist --exclude=./.dart_tool -cf - . | tar -C /work -xf -
cd /work
flutter pub get
flutter build linux --release
cp -a build/linux/x64/release/bundle "$ROOT/app"

# --- 2. Self-contained Python with the server ---
uv python install 3.12 --install-dir /tmp/uvpython
cp -a "$(ls -d /tmp/uvpython/cpython-3.12*-linux-x86_64-gnu | head -1)" "$ROOT/server/python"
PY="$ROOT/server/python/bin/python3"
cp -a /src/pyproject.toml /src/uv.lock /src/README.md /src/LICENSE /src/lumen /tmp/srccopy/
cd /tmp/srccopy
uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/requirements.txt
uv pip install --python "$PY" --break-system-packages --compile-bytecode -r /tmp/requirements.txt
uv pip install --python "$PY" --break-system-packages --compile-bytecode --no-deps .
# Parts of the standard library a server never uses
rm -rf "$ROOT"/server/python/lib/python3.12/test "$ROOT"/server/python/lib/python3.12/idlelib \
       "$ROOT"/server/python/lib/python3.12/tkinter "$ROOT"/server/python/lib/python3.12/turtledemo \
       "$ROOT"/server/python/lib/tcl* "$ROOT"/server/python/lib/tk* "$ROOT"/server/python/lib/itcl* \
       "$ROOT"/server/python/lib/thread* "$ROOT"/server/python/share
"$PY" -c "import lumen.server, lumen.providers; print('server imports ok')"

install -m 755 /src/packaging/linux/lumen-launcher "$ROOT/lumen-launcher"
"$PY" /src/packaging/linux/make_icon.py /tmp/icons 64 128 256 512
mkdir -p "$OUT"

# --- 3. .deb ---
DEB=/tmp/deb
rm -rf "$DEB" && mkdir -p "$DEB/opt" "$DEB/usr/bin" "$DEB/usr/share/applications" "$DEB/DEBIAN"
cp -a "$ROOT" "$DEB/opt/lumen"
ln -s /opt/lumen/lumen-launcher "$DEB/usr/bin/lumen-app"
install -m 755 /src/packaging/linux/lumen-cli "$DEB/usr/bin/lumen"
install -m 644 /src/packaging/linux/lumen.desktop "$DEB/usr/share/applications/lumen.desktop"
for size in 64 128 256 512; do
    install -D -m 644 /tmp/icons/lumen-$size.png "$DEB/usr/share/icons/hicolor/${size}x${size}/apps/lumen.png"
done
cat > "$DEB/DEBIAN/control" <<EOF
Package: lumen
Version: $VERSION
Architecture: amd64
Maintainer: Wasif Farooq <wasif0332@gmail.com>
Installed-Size: $(du -sk "$DEB" | cut -f1)
Depends: libgtk-3-0t64 | libgtk-3-0, ffmpeg, xdg-utils
Section: utils
Priority: optional
Homepage: https://github.com/wasif-farooq/lumen
Description: Local AI assistant for your files
 Find, open and ask about your documents, photos and videos. Lumen indexes
 document text, describes images and video frames, transcribes speech and
 finds duplicate photos. Models run on Ollama (install it separately from
 ollama.com) or any OpenAI-compatible server.
EOF
dpkg-deb --root-owner-group -Zxz -z6 --build "$DEB" "$OUT/lumen_${VERSION}_amd64.deb"

# --- 4. AppImage ---
APPDIR=/tmp/Lumen.AppDir
rm -rf "$APPDIR" && cp -a "$ROOT" "$APPDIR"
mv "$APPDIR/lumen-launcher" "$APPDIR/AppRun"
install -m 644 /src/packaging/linux/lumen.desktop "$APPDIR/lumen.desktop"
install -m 644 /tmp/icons/lumen-256.png "$APPDIR/lumen.png"
ln -s lumen.png "$APPDIR/.DirIcon"
TOOL=/tmp/appimagetool
if [ ! -x "$TOOL" ]; then
    curl -fsSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$TOOL"
fi
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "$OUT/Lumen-${VERSION}-x86_64.AppImage"

ls -lh "$OUT"
