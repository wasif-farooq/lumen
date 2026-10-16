import 'dart:io';

import 'package:flutter/services.dart';
import 'package:lumen_app/shared/theme.dart';

/// A recorded API answer from test/fixtures.
String fixture(String name) => File('test/fixtures/$name.json').readAsStringSync();

/// The app's fonts (and Material icons), so screenshots look like the real app.
Future<void> loadFonts() async {
  Future<void> family(String name, List<String> files) async {
    final loader = FontLoader(name);
    for (final f in files) {
      loader.addFont(Future.value(ByteData.sublistView(File('assets/fonts/$f').readAsBytesSync())));
    }
    await loader.load();
  }

  await family(sans, ['IBMPlexSans-Regular.ttf', 'IBMPlexSans-Medium.ttf', 'IBMPlexSans-SemiBold.ttf']);
  await family(mono, ['IBMPlexMono-Regular.ttf', 'IBMPlexMono-Medium.ttf']);
  final icons = FontLoader('MaterialIcons')
    ..addFont(Future.value(ByteData.sublistView(
        File('${Platform.environment['FLUTTER_ROOT']}/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf').readAsBytesSync())));
  await icons.load();
}
