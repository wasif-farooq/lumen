import 'dart:async';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../api.dart';
import '../app_state.dart';
import '../theme.dart';
import '../widgets/cards.dart';
import '../widgets/common.dart';
import '../widgets/index_progress.dart';

/// Sync: what is indexed and the live indexing run. Preferences live in SettingsScreen.
class IndexScreen extends StatefulWidget {
  const IndexScreen({super.key, required this.state, this.embedded = false});
  final AppState state;
  final bool embedded; // inside the Settings tabs: no page title

  @override
  State<IndexScreen> createState() => _IndexScreenState();
}

class _IndexScreenState extends State<IndexScreen> {
  Map<String, dynamic>? settings;
  Map<String, dynamic>? progress;
  Timer? _poll;
  String? error;

  AppState get s => widget.state;

  @override
  void initState() {
    super.initState();
    _load();
    _poll = Timer.periodic(const Duration(seconds: 2), (_) => _tick());
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final r = await Future.wait([s.api.settings(), s.api.indexProgress()]);
      await s.refreshStatus();
      if (!mounted) return;
      setState(() {
        settings = r[0];
        progress = r[1];
      });
    } catch (e) {
      setState(() => error = '$e');
    }
  }

  Future<void> _tick() async {
    final wasRunning = progress?['running'] == true;
    try {
      final p = await s.api.indexProgress();
      if (!mounted) return;
      setState(() => progress = p);
      if (wasRunning || p['running'] == true) await s.refreshStatus();
    } catch (_) {}
  }

  List<String> get _roots => [for (final r in (settings?['roots'] as List? ?? [])) '$r'];

  /// Save the folder list, then re-index so new folders get added and removed ones drop out.
  Future<void> _setFolders(List<String> roots, String done) async {
    try {
      final saved = await s.api.saveSettings({'roots': roots});
      if (mounted) setState(() => settings = saved);
      await s.api.runIndex();
      await _tick();
      _toast(done);
    } on ApiException catch (e) {
      // A folder that could not be added needs to be seen, not flash by in a snackbar
      if (mounted) {
        await showDialog(
          context: context,
          builder: (_) => AlertDialog(
            title: const Text('Folder not changed'),
            content: Text(e.message, style: const TextStyle(color: C.text3)),
            actions: [FilledButton(onPressed: () => Navigator.pop(context), child: const Text('OK'))],
          ),
        );
      }
    } catch (e) {
      _toast('Could not save: $e');
    }
  }

  Future<void> _addFolder() async {
    String? dir;
    try {
      dir = await getDirectoryPath(confirmButtonText: 'Index this folder');
    } catch (_) {
      dir = await _askPath(); // no native picker available
    }
    if (dir == null || dir.isEmpty) return;
    await _setFolders([..._roots, dir], 'Added ${shortPath(dir)}. Indexing it now…');
  }

  Future<void> _removeFolder(String path, int files) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('Stop indexing ${shortPath(path)}?'),
        content: Text(
          'Its $files files will no longer show up in search. The files themselves are not touched.',
          style: const TextStyle(color: C.text3),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Stop indexing')),
        ],
      ),
    );
    if (ok != true) return;
    await _setFolders(_roots.where((r) => r != path).toList(), 'Removed ${shortPath(path)}.');
  }

  Future<String?> _askPath({String title = 'Add a folder', String action = 'Add'}) {
    final ctrl = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          style: monoStyle(size: 14, color: C.text),
          decoration: const InputDecoration(hintText: '~/Pictures', border: OutlineInputBorder()),
          onSubmitted: (v) => Navigator.pop(context, v.trim()),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, ctrl.text.trim()), child: Text(action)),
        ],
      ),
    );
  }

  void _toast(String msg) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  bool _stopping = false;

  Future<void> _stop() async {
    setState(() => _stopping = true);
    try {
      await s.api.stopIndex();
      await _tick();
      await s.refreshStatus();
      _toast('Indexing stopped. Finished work is saved.');
    } catch (e) {
      _toast('Could not stop: $e');
    } finally {
      if (mounted) setState(() => _stopping = false);
    }
  }

  bool _pauseBusy = false;

  Future<void> _togglePause() async {
    final paused = progress?['paused'] == true || progress?['pausing'] == true;
    setState(() => _pauseBusy = true);
    try {
      await (paused ? s.api.resumeIndex() : s.api.pauseIndex());
      await _tick();
    } catch (e) {
      _toast('Could not ${paused ? 'resume' : 'pause'}: $e');
    } finally {
      if (mounted) setState(() => _pauseBusy = false);
    }
  }

  /// Run a folder/exclusion change, then refresh what the screen shows.
  Future<void> _change(Future<void> Function() action, String Function() done) async {
    try {
      await action();
      final r = await Future.wait([s.api.settings(), s.refreshStatus()]);
      await _tick();
      if (mounted) setState(() => settings = r[0] as Map<String, dynamic>);
      _toast(done());
    } on ApiException catch (e) {
      _toast(e.message);
    } catch (e) {
      _toast('$e');
    }
  }

  Future<void> _toggleFolderSync(String path, bool paused) => _change(
        () => paused ? s.api.resumeFolder(path) : s.api.pauseFolder(path),
        () => paused ? 'Syncing ${shortPath(path)} again. Catching up now…' : 'Paused syncing ${shortPath(path)}. Its files stay searchable.',
      );

  Future<void> _clearFolder(String path, int files, bool paused) async {
    final choice = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('Clear indexed data for ${shortPath(path)}?'),
        content: Text(
          'Removes what was indexed for its $files files: text, image descriptions, transcripts and fingerprints. '
          'The files themselves are not touched.'
          '${paused ? '\n\nThe folder is paused, so it stays empty until you resume syncing.' : '\n\nRe-indexing builds it again from scratch.'}',
          style: const TextStyle(color: C.text3),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          if (!paused) OutlinedButton(onPressed: () => Navigator.pop(context, 'clear'), child: const Text('Clear only')),
          FilledButton(onPressed: () => Navigator.pop(context, paused ? 'clear' : 'reindex'), child: Text(paused ? 'Clear' : 'Clear and re-index')),
        ],
      ),
    );
    if (choice == null) return;
    await _change(() => s.api.clearFolder(path, reindex: choice == 'reindex'),
        () => 'Cleared ${shortPath(path)}${choice == 'reindex' ? '. Re-indexing it now…' : '.'}');
  }

  List<String> get _excluded => [for (final e in (settings?['excluded'] as List? ?? [])) '$e'];

  Future<void> _exclude(bool folder) async {
    String? path;
    try {
      path = folder ? await getDirectoryPath(confirmButtonText: 'Keep out of the index') : (await openFile(confirmButtonText: 'Keep out of the index'))?.path;
    } catch (_) {
      path = await _askPath(title: folder ? 'Exclude a folder' : 'Exclude a file', action: 'Exclude');
    }
    if (path == null || path.isEmpty) return;
    var removed = 0;
    await _change(() async => removed = await s.api.excludePath(path!),
        () => 'Excluded ${shortPath(path!)}${removed > 0 ? ' and removed $removed indexed ${removed == 1 ? 'file' : 'files'}' : ''}.');
  }

  Future<void> _include(String path) => _change(() => s.api.includePath(path), () => 'Including ${shortPath(path)} again. Indexing it now…');

  Future<void> _reindex() async {
    await s.api.runIndex();
    await _tick();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: s,
      builder: (context, _) {
        final st = s.status ?? {};
        final idx = st['index'] ?? {};
        final last = st['last_index'];
        final running = progress?['running'] == true;
        final paused = running && (progress?['paused'] == true || progress?['pausing'] == true);
        final lines = (progress?['lines'] as List? ?? []).cast<String>();
        return ListView(
          padding: EdgeInsets.fromLTRB(32, widget.embedded ? 20 : 28, 32, 40),
          children: [
            Wrap(alignment: WrapAlignment.spaceBetween, crossAxisAlignment: WrapCrossAlignment.center, runSpacing: 12, children: [
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                if (!widget.embedded) const Text('Sync', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
                Text(
                  running ? (paused ? 'Indexing paused' : 'Indexing now…') : (last == null ? 'Not indexed from the app yet' : 'Last run ${_ago(last['at'])}'),
                  style: const TextStyle(color: C.text3),
                ),
              ]),
              Row(mainAxisSize: MainAxisSize.min, children: [
                if (running) ...[
                  OutlinedButton.icon(
                    onPressed: _pauseBusy || _stopping ? null : _togglePause,
                    icon: Icon(paused ? Icons.play_arrow_rounded : Icons.pause_rounded, size: 18),
                    label: Text(paused ? 'Resume' : 'Pause'),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton.icon(
                    onPressed: _stopping ? null : _stop,
                    icon: const Icon(Icons.stop_rounded, size: 18),
                    label: Text(_stopping ? 'Stopping…' : 'Stop'),
                  ),
                  const SizedBox(width: 8),
                ],
                FilledButton.icon(
                  onPressed: running ? null : _reindex,
                  icon: running
                      ? (paused
                          ? const Icon(Icons.pause_rounded, size: 18)
                          : const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: C.text3)))
                      : const Icon(Icons.refresh, size: 18),
                  label: Text(running ? (paused ? 'Paused' : 'Indexing…') : 'Re-index now'),
                ),
              ]),
            ]),
            if (error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(error!, style: const TextStyle(color: C.red))),
            const SizedBox(height: 24),
            LayoutBuilder(builder: (context, c) {
              final cols = c.maxWidth > 900 ? 5 : (c.maxWidth > 560 ? 3 : 2);
              final w = (c.maxWidth - (cols - 1) * 12) / cols;
              return Wrap(spacing: 12, runSpacing: 12, children: [
                for (final (n, label) in [
                  (idx['files'], 'Files'),
                  (idx['with_text'], 'With searchable text'),
                  (idx['captioned'], 'Images & scans described'),
                  (idx['media_indexed'], 'Videos indexed'),
                  (idx['transcript_lines'], 'Transcript lines'),
                ])
                  SizedBox(width: w, child: _Stat(value: '${n ?? '–'}', label: label)),
              ]);
            }),
            if (running || lines.isNotEmpty || last != null) ...[
              const SizedBox(height: 20),
              IndexProgressCard(
                progress: progress ?? const {},
                lastRun: last is Map ? Map<String, dynamic>.from(last) : null,
                enabled: {
                  'scan',
                  if (settings?['captions'] ?? true) 'captions',
                  if (settings?['visual'] ?? true) 'visual',
                  if (settings?['media'] ?? true) 'media',
                  'passages',
                },
              ),
            ],
            const SizedBox(height: 20),
            TwoColumns(children: [
              CardColumn(children: [
                SectionCard(
                  title: 'Folders',
                  trailing: OutlinedButton.icon(
                    onPressed: running ? null : _addFolder,
                    style: OutlinedButton.styleFrom(minimumSize: const Size(0, 36)),
                    icon: const Icon(Icons.add, size: 16),
                    label: const Text('Add folder'),
                  ),
                  child: Column(children: [
                    for (final f in (st['folders'] as List? ?? []))
                      Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.fromLTRB(12, 4, 4, 4),
                        constraints: const BoxConstraints(minHeight: 48),
                        decoration: BoxDecoration(color: C.surface2, borderRadius: BorderRadius.circular(10)),
                        child: Row(children: [
                          const Icon(Icons.folder_outlined, size: 18, color: C.accent),
                          const SizedBox(width: 12),
                          Expanded(child: Text(shortPath(f['path']), style: monoStyle(size: 13, color: f['paused'] == true ? C.text3 : C.text))),
                          if (f['paused'] == true) ...[
                            const Icon(Icons.pause_circle_outline, size: 15, color: C.blue),
                            const SizedBox(width: 4),
                            const Text('Paused', style: TextStyle(fontSize: 13, color: C.blue)),
                            const SizedBox(width: 10),
                          ],
                          Text('${f['files']} files', style: const TextStyle(fontSize: 13, color: C.text3)),
                          const SizedBox(width: 4),
                          _FolderMenu(
                            path: f['path'],
                            paused: f['paused'] == true,
                            enabled: !running,
                            canRemove: (st['folders'] as List).length > 1,
                            onSync: () => _toggleFolderSync(f['path'], f['paused'] == true),
                            onClear: () => _clearFolder(f['path'], f['files'] ?? 0, f['paused'] == true),
                            onRemove: () => _removeFolder(f['path'], f['files'] ?? 0),
                          ),
                        ]),
                      ),
                    const Align(
                      alignment: Alignment.centerLeft,
                      child: Text('Hidden folders, node_modules, build and cache folders are skipped.', style: TextStyle(fontSize: 13, color: C.muted)),
                    ),
                    if (running)
                      const Padding(
                        padding: EdgeInsets.only(top: 6),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: Text('Folder changes are available once indexing finishes or is stopped.', style: TextStyle(fontSize: 13, color: C.muted)),
                        ),
                      ),
                  ]),
                ),
              ]),
              CardColumn(children: [
                SectionCard(
                  title: 'Kept out of the index',
                  trailing: PopupMenuButton<bool>(
                    enabled: !running,
                    tooltip: 'Exclude a file or folder',
                    onSelected: _exclude,
                    itemBuilder: (_) => const [
                      PopupMenuItem(value: false, child: Text('Exclude a file…')),
                      PopupMenuItem(value: true, child: Text('Exclude a folder…')),
                    ],
                    child: IgnorePointer(
                      child: OutlinedButton.icon(
                        onPressed: running ? null : () {},
                        style: OutlinedButton.styleFrom(minimumSize: const Size(0, 36)),
                        icon: const Icon(Icons.block, size: 16),
                        label: const Text('Exclude'),
                      ),
                    ),
                  ),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    if (_excluded.isEmpty)
                      const Text('Nothing excluded. Files and folders you exclude are removed from search and skipped by later runs.',
                          style: TextStyle(fontSize: 13, color: C.muted)),
                    for (final e in _excluded)
                      Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.fromLTRB(12, 4, 4, 4),
                        constraints: const BoxConstraints(minHeight: 44),
                        decoration: BoxDecoration(color: C.surface2, borderRadius: BorderRadius.circular(10)),
                        child: Row(children: [
                          const Icon(Icons.block, size: 16, color: C.muted),
                          const SizedBox(width: 12),
                          Expanded(child: Text(shortPath(e), style: monoStyle(size: 13, color: C.text2), overflow: TextOverflow.ellipsis)),
                          TextButton(onPressed: running ? null : () => _include(e), child: const Text('Include again')),
                        ]),
                      ),
                  ]),
                ),
              ]),
            ]),
          ],
        );
      },
    );
  }

  String _ago(dynamic at) {
    if (at is! num) return '';
    final mins = (DateTime.now().millisecondsSinceEpoch / 1000 - at) ~/ 60;
    if (mins < 1) return 'just now';
    if (mins < 60) return '$mins minutes ago';
    if (mins < 60 * 24) return '${mins ~/ 60} hours ago';
    return '${mins ~/ (60 * 24)} days ago';
  }
}

/// Per-folder actions: pause/resume syncing, clear its indexed data, stop indexing it.
class _FolderMenu extends StatelessWidget {
  const _FolderMenu({
    required this.path,
    required this.paused,
    required this.enabled,
    required this.canRemove,
    required this.onSync,
    required this.onClear,
    required this.onRemove,
  });
  final String path;
  final bool paused, enabled, canRemove;
  final VoidCallback onSync, onClear, onRemove;

  @override
  Widget build(BuildContext context) => PopupMenuButton<String>(
        enabled: enabled,
        tooltip: 'Actions for ${shortPath(path)}',
        icon: Icon(Icons.more_vert, size: 18, color: enabled ? C.text3 : C.line2),
        onSelected: (v) => switch (v) { 'sync' => onSync(), 'clear' => onClear(), _ => onRemove() },
        itemBuilder: (_) => [
          PopupMenuItem(
            value: 'sync',
            child: _MenuRow(paused ? Icons.play_arrow_rounded : Icons.pause_rounded, paused ? 'Resume syncing' : 'Pause syncing',
                paused ? 'Pick up changes since it was paused' : 'Keep its files searchable, stop re-scanning'),
          ),
          const PopupMenuItem(value: 'clear', child: _MenuRow(Icons.cleaning_services_outlined, 'Clear indexed data…', 'Start this folder from scratch')),
          const PopupMenuDivider(),
          PopupMenuItem(
            value: 'remove',
            enabled: canRemove,
            child: const _MenuRow(Icons.close, 'Stop indexing this folder…', 'Remove it from the folder list'),
          ),
        ],
      );
}

class _MenuRow extends StatelessWidget {
  const _MenuRow(this.icon, this.title, this.subtitle);
  final IconData icon;
  final String title, subtitle;
  @override
  Widget build(BuildContext context) => Row(children: [
        Icon(icon, size: 18, color: C.text3),
        const SizedBox(width: 12),
        Flexible(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            Text(title),
            Text(subtitle, style: const TextStyle(fontSize: 12, color: C.muted)),
          ]),
        ),
      ]);
}

class _Stat extends StatelessWidget {
  const _Stat({required this.value, required this.label});
  final String value, label;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(color: C.surface, borderRadius: BorderRadius.circular(12), border: Border.all(color: C.line)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(value, style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w600)),
          Text(label, style: const TextStyle(fontSize: 13, color: C.text3), maxLines: 1, overflow: TextOverflow.ellipsis),
        ]),
      );
}
