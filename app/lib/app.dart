import 'dart:io';

import 'package:flutter/material.dart';

import 'core/errors/error_reporter.dart';
import 'features/shell/desktop_home.dart';
import 'features/shell/mobile_home.dart';
import 'shared/theme.dart';
import 'shared/widgets/zoom.dart';

bool get isDesktop => Platform.isLinux || Platform.isMacOS || Platform.isWindows;

class LumenApp extends StatelessWidget {
  const LumenApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Lumen',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(),
        scaffoldMessengerKey: ErrorReporter.messenger,
        builder: isDesktop ? (context, child) => Zoom(child: child!) : null,
        home: isDesktop ? const DesktopHome() : const MobileHome(),
      );
}
