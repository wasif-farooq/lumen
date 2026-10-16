import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/app_state.dart';

/// The Models tab's state: providers, which model does each job, connection tests, model
/// checks and Ollama downloads (polled every second while one runs). Actions throw [ApiError].
class ModelsController extends ChangeNotifier {
  ModelsController(this.app);

  final AppState app;
  Api get api => app.api;

  Map<String, dynamic>? data;
  Object? loadError;
  final Map<String, Map<String, dynamic>> tests = {}; // provider id -> {ok, message} or {busy}
  final Map<String, Map<String, dynamic>> checks = {}; // role -> last compatibility check of its model
  Timer? _pullPoll;
  bool _disposed = false;

  @override
  void dispose() {
    _disposed = true;
    _pullPoll?.cancel();
    super.dispose();
  }

  void changed() {
    if (!_disposed) notifyListeners();
  }

  List<Map<String, dynamic>> get providers => [for (final p in data?['providers'] as List? ?? const []) Map<String, dynamic>.from(p as Map)];
  Map<String, dynamic> get roles => Map<String, dynamic>.from(data?['roles'] as Map? ?? const {});
  List<Map<String, dynamic>> get pulls => [for (final p in data?['pulls'] as List? ?? const []) Map<String, dynamic>.from(p as Map)];
  List<String> get speechModels => [for (final m in data?['speech_models'] as List? ?? const []) '$m'];
  Map<String, dynamic>? provider(Object? id) => providers.where((p) => p['id'] == id).firstOrNull;
  Map<String, dynamic> role(String id) => Map<String, dynamic>.from(roles[id] as Map? ?? const {});

  /// The last check of the model a job uses now (null when it was another model).
  Map<String, dynamic>? checkOf(String id) {
    final c = checks[id];
    return c != null && c['model'] == role(id)['model'] ? c : null;
  }

  Future<void> load() async {
    try {
      data = await api.providers();
      loadError = null;
      changed();
      // Keep polling while a model download runs
      final pulling = pulls.any((p) => p['done'] != true);
      if (pulling && _pullPoll == null) {
        _pullPoll = Timer.periodic(const Duration(seconds: 1), (_) => unawaited(load()));
      } else if (!pulling) {
        _pullPoll?.cancel();
        _pullPoll = null;
      }
    } on ApiError catch (e) {
      loadError = e;
      changed();
    }
  }

  /// Can we reach this provider? The result shows under it.
  Future<void> test(String id) async {
    tests[id] = {'busy': true};
    changed();
    try {
      tests[id] = await api.testProvider(id);
    } on ApiError catch (e) {
      tests[id] = {'ok': false, 'message': e.message};
    }
    changed();
  }

  Future<void> useModel(String role, String provider, String model) async {
    await api.setRole(role, provider, model);
    await Future.wait([load(), app.refreshStatus()]);
  }

  Future<void> setSpeech(String model) => useModel('speech', 'local', model);

  Future<void> removeProvider(String id) async {
    await api.deleteProvider(id);
    await load();
  }

  Future<void> pull(String model) async {
    await api.pullModel(model);
    await load();
  }
}
