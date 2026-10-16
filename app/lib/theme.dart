import 'package:flutter/material.dart';

/// Colors from the Lumen design canvas.
class C {
  static const bg = Color(0xFF0F1113);
  static const panel = Color(0xFF13161A);
  static const surface = Color(0xFF171B20);
  static const surface2 = Color(0xFF1D2126);
  static const raised = Color(0xFF20252B);
  static const bubble = Color(0xFF262B31);
  static const line = Color(0xFF252A30);
  static const line2 = Color(0xFF2F353C);
  static const text = Color(0xFFE9ECEF);
  static const text2 = Color(0xFFB6BEC6);
  static const text3 = Color(0xFFA3ABB4);
  static const muted = Color(0xFF8A939D);
  static const accent = Color(0xFFF0A53A);
  static const onAccent = Color(0xFF1A1204);
  static const accentSoft = Color(0xFF221D15);
  static const blue = Color(0xFF8DBBFF);
  static const toolBg = Color(0xFF151A20);
  static const toolLine = Color(0xFF243041);
  static const green = Color(0xFF5CC28A);
  static const red = Color(0xFFFF8A80);
  static const markBg = Color(0x38F0A53A);
  static const markFg = Color(0xFFFFD9A0);
}

const sans = 'IBMPlexSans';
const mono = 'IBMPlexMono';

TextStyle monoStyle({double size = 12, Color color = C.text3, FontWeight weight = FontWeight.w400}) =>
    TextStyle(fontFamily: mono, fontSize: size, color: color, fontWeight: weight);

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: C.accent,
    brightness: Brightness.dark,
  ).copyWith(
    primary: C.accent,
    onPrimary: C.onAccent,
    surface: C.surface,
    onSurface: C.text,
    outline: C.line2,
    outlineVariant: C.line,
    secondary: C.blue,
    error: C.red,
  );
  final base = ThemeData(useMaterial3: true, colorScheme: scheme, fontFamily: sans, scaffoldBackgroundColor: C.bg);
  return base.copyWith(
    textTheme: base.textTheme.apply(bodyColor: C.text, displayColor: C.text, fontFamily: sans),
    dividerColor: C.line,
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: C.accent,
        foregroundColor: C.onAccent,
        minimumSize: const Size(44, 44),
        textStyle: const TextStyle(fontFamily: sans, fontWeight: FontWeight.w600, fontSize: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: C.text,
        minimumSize: const Size(44, 44),
        side: const BorderSide(color: C.line2),
        textStyle: const TextStyle(fontFamily: sans, fontSize: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(foregroundColor: C.blue, textStyle: const TextStyle(fontFamily: sans, fontSize: 13)),
    ),
    inputDecorationTheme: const InputDecorationTheme(
      border: InputBorder.none,
      hintStyle: TextStyle(color: C.muted),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? C.onAccent : C.text3),
      trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? C.accent : C.surface2),
    ),
    snackBarTheme: const SnackBarThemeData(backgroundColor: C.raised, contentTextStyle: TextStyle(color: C.text)),
    bottomSheetTheme: const BottomSheetThemeData(backgroundColor: C.surface, showDragHandle: true),
    dialogTheme: const DialogThemeData(backgroundColor: C.surface),
  );
}
