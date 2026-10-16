import 'package:flutter/material.dart';

import 'app.dart';
import 'core/errors/error_reporter.dart';
import 'core/logging/log.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  Log.toFile();
  ErrorReporter.install();
  const Log('app').info('Lumen app starting');
  runApp(const LumenApp());
}
