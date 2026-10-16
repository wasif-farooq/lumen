import 'package:flutter/foundation.dart';

import '../../core/app_state.dart';
import '../../core/logging/log.dart';

/// Settings → General: indexing and power preferences (saved as they change) and paired phones.
class GeneralController extends ChangeNotifier {
  GeneralController(this.app);

  final AppState app;
  Api get api => app.api;

  Map<String, dynamic>? settings;
  List<Map<String, dynamic>> devices = [];
  Object? loadError;
  bool _disposed = false;

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  void _changed() {
    if (!_disposed) notifyListeners();
  }

  Future<void> load() async {
    try {
      final r = await Future.wait([api.settings(), api.devices().catchError((_) => <Map<String, dynamic>>[])]);
      await app.refreshStatus();
      settings = r[0] as Map<String, dynamic>;
      devices = r[1] as List<Map<String, dynamic>>;
      loadError = null;
    } on ApiError catch (e) {
      loadError = e;
    }
    _changed();
  }

  /// Show the change at once, save it, then show what the server kept. Throws [ApiError].
  Future<void> set(String key, Object value) async {
    settings = {...?settings, key: value};
    _changed();
    final saved = await api.saveSettings({key: value});
    await app.refreshStatus();
    settings = saved;
    _changed();
  }

  Future<void> refreshDevices() async {
    devices = await api.devices();
    _changed();
  }

  Future<void> unpair(String id) async {
    await api.unpair(id);
    await refreshDevices();
  }

  /// For a bug report: the server's diagnostics (versions, models, its log) and the app's log.
  Future<String> diagnostics() async {
    final out = StringBuffer('Lumen diagnostics\n');
    try {
      final d = await api.diagnostics();
      out.writeln('server ${d['version']} · Python ${d['python']} · ${d['platform']}');
      out.writeln('models ${d['roles']} · power ${d['power_mode']}${d['cpu_only'] == true ? ' (CPU only)' : ''}');
      out.writeln('folders ${d['folders']} · indexing ${d['indexing']} · logs in ${d['log_dir']}');
      final logs = Map<String, dynamic>.from(d['logs'] as Map? ?? const {});
      for (final e in logs.entries) {
        final lines = [for (final l in e.value as List? ?? const []) '$l'];
        if (lines.isEmpty) continue;
        out.writeln('\n--- ${e.key} log (last ${lines.length.clamp(0, 80)} lines) ---');
        out.writeln(lines.skip(lines.length > 80 ? lines.length - 80 : 0).join('\n'));
      }
    } on ApiError catch (e) {
      out.writeln('server diagnostics unavailable: ${e.message}');
    }
    out.writeln('\n--- app log ---');
    out.writeln(Log.recent.isEmpty ? '(empty)' : Log.recent.join('\n'));
    return out.toString();
  }
}
