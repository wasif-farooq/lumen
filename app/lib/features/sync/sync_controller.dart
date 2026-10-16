import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/app_state.dart';

/// What the Sync tab shows and does: the folder settings, the live index run (polled every
/// 2 s), and folder / exclusion changes. Actions throw [ApiError]; the screen shows it.
class SyncController extends ChangeNotifier {
  SyncController(this.app);

  final AppState app;
  Api get api => app.api;

  Map<String, dynamic>? settings;
  Map<String, dynamic>? progress;
  Object? loadError;
  bool stopping = false, pauseBusy = false;
  Timer? _poll;
  bool _disposed = false;

  void start() {
    unawaited(load());
    _poll = Timer.periodic(const Duration(seconds: 2), (_) => unawaited(tick()));
  }

  @override
  void dispose() {
    _disposed = true;
    _poll?.cancel();
    super.dispose();
  }

  void _changed() {
    if (!_disposed) notifyListeners();
  }

  // ---------- what the screen shows ----------

  bool get running => progress?['running'] == true;
  bool get paused => running && (progress?['paused'] == true || progress?['pausing'] == true);
  List<String> get lines => [for (final l in progress?['lines'] as List? ?? const []) '$l'];
  List<String> get roots => [for (final r in settings?['roots'] as List? ?? const []) '$r'];
  List<String> get excluded => [for (final e in settings?['excluded'] as List? ?? const []) '$e'];

  /// Index passes switched on in the settings (the progress card shows only these).
  Set<String> get enabledPhases => {
        'scan',
        if (settings?['captions'] as bool? ?? true) 'captions',
        if (settings?['visual'] as bool? ?? true) 'visual',
        if (settings?['media'] as bool? ?? true) 'media',
        'passages',
      };

  // ---------- loading ----------

  Future<void> load() async {
    try {
      final r = await Future.wait([api.settings(), api.indexProgress()]);
      await app.refreshStatus();
      settings = r[0];
      progress = r[1];
      loadError = null;
    } on ApiError catch (e) {
      loadError = e;
    }
    _changed();
  }

  /// Poll the index run; while it runs, also the status (file counts in the sidebar).
  Future<void> tick() async {
    final wasRunning = running;
    try {
      progress = await api.indexProgress();
      _changed();
      if (wasRunning || running) await app.refreshStatus();
    } on ApiError {
      // logged by the API client; the next poll tries again
    }
  }

  Future<void> _reloadSettings() async {
    final r = await Future.wait([api.settings(), app.refreshStatus()]);
    await tick();
    settings = r[0] as Map<String, dynamic>;
    _changed();
  }

  // ---------- the index run ----------

  Future<void> reindex() async {
    await api.runIndex();
    await tick();
  }

  Future<void> stop() async {
    stopping = true;
    _changed();
    try {
      await api.stopIndex();
      await tick();
      await app.refreshStatus();
    } finally {
      stopping = false;
      _changed();
    }
  }

  /// Pause a running index, or resume a paused one. Returns what was asked: 'pause' / 'resume'.
  Future<void> togglePause() async {
    final resume = progress?['paused'] == true || progress?['pausing'] == true;
    pauseBusy = true;
    _changed();
    try {
      await (resume ? api.resumeIndex() : api.pauseIndex());
      await tick();
    } finally {
      pauseBusy = false;
      _changed();
    }
  }

  // ---------- folders and exclusions ----------

  /// Save the folder list, then re-index so new folders get added and removed ones drop out.
  Future<void> setFolders(List<String> folders) async {
    settings = await api.saveSettings({'roots': folders});
    _changed();
    await api.runIndex();
    await tick();
  }

  Future<void> toggleFolderSync(String path, bool paused) async {
    await (paused ? api.resumeFolder(path) : api.pauseFolder(path));
    await _reloadSettings();
  }

  Future<void> clearFolder(String path, {required bool reindex}) async {
    await api.clearFolder(path, reindex: reindex);
    await _reloadSettings();
  }

  /// Keep a file or folder out of the index; returns how many indexed files it removed.
  Future<int> exclude(String path) async {
    final removed = await api.excludePath(path);
    await _reloadSettings();
    return removed;
  }

  Future<void> include(String path) async {
    await api.includePath(path);
    await _reloadSettings();
  }
}
