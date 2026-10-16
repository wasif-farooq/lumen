import 'dart:collection';
import 'dart:io';

import 'package:flutter/foundation.dart';

enum Level { debug, info, warning, error }

/// The app's log: the console while developing, the last lines in memory (for "Copy
/// diagnostics"), and on desktop a file next to the server's logs:
/// ~/.local/state/lumen/app.log (LUMEN_LOG_DIR moves it).
class Log {
  const Log(this.name);
  final String name;

  static final recent = ListQueue<String>();
  static const _keep = 300;
  static File? _file;
  static const _maxBytes = 1000000;

  /// Also write to the log file (desktop). Called once at start.
  static void toFile() {
    try {
      final f = file;
      if (f == null) return;
      f.parent.createSync(recursive: true);
      if (f.existsSync() && f.lengthSync() > _maxBytes) f.renameSync('${f.path}.1');
      _file = f;
    } on FileSystemException catch (e) {
      debugPrint('lumen: no log file ($e)');
    }
  }

  /// Where the app's (and the server's) logs are, on desktop.
  static Directory? get folder {
    if (!(Platform.isLinux || Platform.isMacOS || Platform.isWindows)) return null;
    final env = Platform.environment;
    if ((env['LUMEN_LOG_DIR'] ?? '').isNotEmpty) return Directory(env['LUMEN_LOG_DIR']!);
    final state = env['XDG_STATE_HOME'] ?? '${env['HOME']}/.local/state';
    return Directory('$state/lumen');
  }

  static File? get file => folder == null ? null : File('${folder!.path}/app.log');

  void debug(String message) => _write(Level.debug, message);
  void info(String message) => _write(Level.info, message);
  void warning(String message, [Object? error]) => _write(Level.warning, message, error);
  void error(String message, [Object? error, StackTrace? stack]) => _write(Level.error, message, error, stack);

  void _write(Level level, String message, [Object? error, StackTrace? stack]) {
    final line = StringBuffer('${DateTime.now().toIso8601String()} ${level.name.toUpperCase().padRight(7)} $name $message');
    if (error != null) line.write(' ($error)');
    if (stack != null) line.write('\n$stack');
    final text = line.toString();
    if (kDebugMode && level != Level.debug) debugPrint(text);
    if (level == Level.debug) return;
    recent.addLast(text);
    while (recent.length > _keep) {
      recent.removeFirst();
    }
    try {
      _file?.writeAsStringSync('$text\n', mode: FileMode.append, flush: level == Level.error);
    } on FileSystemException {
      _file = null; // disk full or folder gone: keep running without the file
    }
  }
}
