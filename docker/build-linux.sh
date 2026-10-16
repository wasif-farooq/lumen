#!/bin/sh
# Copy the app source (read-only mount at /src) and build it here, so the host's
# .dart_tool/ and build/ folders, which hold host paths, are never touched.
set -e
tar -C /src --exclude=./build --exclude=./dist --exclude=./.dart_tool -cf - . | tar -C /work -xf -
flutter pub get
flutter build linux --release "$@"
rm -rf /out/* && cp -a build/linux/x64/release/bundle/. /out/
echo "Built: app/dist/linux/lumen"
