import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../logging/log.dart';

final _log = Log('crash');

/// Catches what nothing else caught (a widget failing to build, an async error nobody awaited):
/// it goes to the log, and people see one calm line instead of a red screen or nothing.
class ErrorReporter {
  /// The app's ScaffoldMessenger, so errors from anywhere can be shown.
  static final messenger = GlobalKey<ScaffoldMessengerState>();

  static void install() {
    final previous = FlutterError.onError;
    FlutterError.onError = (details) {
      _log.error('Flutter: ${details.exceptionAsString()}', null, details.stack);
      if (kDebugMode) previous?.call(details);
    };
    PlatformDispatcher.instance.onError = (error, stack) {
      report(error, stack);
      return true;
    };
  }

  static void report(Object error, StackTrace? stack) {
    _log.error('Uncaught', error, stack);
    messenger.currentState?.showSnackBar(
      const SnackBar(content: Text('Something went wrong in the app. The details are in its log.')),
    );
  }
}
