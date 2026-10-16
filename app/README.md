# Lumen app (Flutter)

Desktop (Linux) and phone app for the Lumen agent. The design lives on the
"OS Operator App UI" canvas (made before the rename to Lumen); screenshots of the built screens are in `test/screens/`.

## 1. Start the API on the laptop

```bash
cd ~/work/personal/os-operator
LUMEN_DATA=./data uv run --env-file .env lumen serve --lan   # drop --lan to keep phones out
```

Or install it as a service: `deploy/lumen-api.service` (instructions at its top).
The desktop app can also start it for you ("Start service" when it isn't running).

## 2. Desktop app

One-time: `sudo apt install -y clang ninja-build libgtk-3-dev`

```bash
export PATH=$HOME/development/flutter/bin:$PATH
cd app
flutter run -d linux                 # development
flutter build linux --release        # binary: build/linux/x64/release/bundle/lumen
```

## 3. Phone app (Android)

One-time: install Android Studio (or the command-line SDK), then `flutter doctor --android-licenses`.

```bash
flutter run -d <your-phone>          # USB debugging on
flutter build apk --release          # build/app/outputs/flutter-apk/app-release.apk
```

On the laptop open **Index & power → Pair a phone**; on the phone pick the laptop
(found automatically on the same Wi-Fi) and type the 6-digit code.

## Tests

```bash
flutter analyze
flutter test                         # renders every screen against recorded API responses
flutter test --update-goldens        # refresh test/screens/*.png after UI changes
```
