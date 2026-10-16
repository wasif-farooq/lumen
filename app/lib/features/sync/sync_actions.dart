import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';

import '../../core/api/api_error.dart';
import '../../core/errors/errors.dart';
import '../../core/errors/run_guarded.dart';
import '../../core/format.dart';
import '../../shared/theme.dart';
import 'sync_controller.dart';

/// What the Sync tab's buttons do: ask when needed, run the change, and say how it went.
class SyncActions {
  SyncActions(this.context, this.c);
  final BuildContext context;
  final SyncController c;

  Future<void> reindex() => runGuarded(context, c.reindex, failure: 'Could not start indexing');

  Future<void> stop() =>
      runGuarded(context, c.stop, failure: 'Could not stop', success: (_) => 'Indexing stopped. Finished work is saved.');

  Future<void> togglePause() {
    final resume = c.progress?['paused'] == true || c.progress?['pausing'] == true;
    return runGuarded(context, c.togglePause, failure: 'Could not ${resume ? 'resume' : 'pause'}');
  }

  Future<void> addFolder() async {
    String? dir;
    try {
      dir = await getDirectoryPath(confirmButtonText: 'Index this folder');
    } on Object {
      dir = await _askPath(); // no native picker available
    }
    if (dir == null || dir.isEmpty) return;
    await _setFolders([...c.roots, dir], 'Added ${shortPath(dir)}. Indexing it now…');
  }

  Future<void> removeFolder(String path, int files) async {
    final ok = await _confirm(
      title: 'Stop indexing ${shortPath(path)}?',
      text: 'Its $files files will no longer show up in search. The files themselves are not touched.',
      action: 'Stop indexing',
    );
    if (ok != true) return;
    await _setFolders(c.roots.where((r) => r != path).toList(), 'Removed ${shortPath(path)}.');
  }

  /// A folder that could not be added needs to be seen, not flash by in a snackbar.
  Future<void> _setFolders(List<String> roots, String done) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await c.setFolders(roots);
      messenger.showSnackBar(SnackBar(content: Text(done)));
    } on ApiError catch (e) {
      if (!context.mounted) return;
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Folder not changed'),
          content: Text(e.hint.isEmpty ? e.message : '${e.message}\n\n${e.hint}', style: const TextStyle(color: C.text3)),
          actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('OK'))],
        ),
      );
    } on Object catch (e, st) {
      logUnexpected('change folders', e, st);
      messenger.showSnackBar(SnackBar(content: Text('Could not save: ${userMessage(e)}')));
    }
  }

  Future<void> toggleFolderSync(String path, bool paused) => runGuarded(
        context,
        () => c.toggleFolderSync(path, paused),
        failure: 'Could not ${paused ? 'resume' : 'pause'} ${shortPath(path)}',
        success: (_) => paused ? 'Syncing ${shortPath(path)} again. Catching up now…' : 'Paused syncing ${shortPath(path)}. Its files stay searchable.',
      );

  Future<void> clearFolder(String path, int files, bool paused) async {
    final choice = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Clear indexed data for ${shortPath(path)}?'),
        content: Text(
          'Removes what was indexed for its $files files: text, image descriptions, transcripts and fingerprints. '
          'The files themselves are not touched.'
          '${paused ? '\n\nThe folder is paused, so it stays empty until you resume syncing.' : '\n\nRe-indexing builds it again from scratch.'}',
          style: const TextStyle(color: C.text3),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          if (!paused) OutlinedButton(onPressed: () => Navigator.pop(ctx, 'clear'), child: const Text('Clear only')),
          FilledButton(onPressed: () => Navigator.pop(ctx, paused ? 'clear' : 'reindex'), child: Text(paused ? 'Clear' : 'Clear and re-index')),
        ],
      ),
    );
    if (choice == null || !context.mounted) return;
    await runGuarded(
      context,
      () => c.clearFolder(path, reindex: choice == 'reindex'),
      failure: 'Could not clear ${shortPath(path)}',
      success: (_) => 'Cleared ${shortPath(path)}${choice == 'reindex' ? '. Re-indexing it now…' : '.'}',
    );
  }

  Future<void> exclude(bool folder) async {
    String? path;
    try {
      path = folder
          ? await getDirectoryPath(confirmButtonText: 'Keep out of the index')
          : (await openFile(confirmButtonText: 'Keep out of the index'))?.path;
    } on Object {
      path = await _askPath(title: folder ? 'Exclude a folder' : 'Exclude a file', action: 'Exclude');
    }
    if (path == null || path.isEmpty || !context.mounted) return;
    final p = path;
    await runGuarded(
      context,
      () => c.exclude(p),
      failure: 'Could not exclude ${shortPath(p)}',
      success: (removed) =>
          'Excluded ${shortPath(p)}${removed > 0 ? ' and removed $removed indexed ${removed == 1 ? 'file' : 'files'}' : ''}.',
    );
  }

  Future<void> include(String path) => runGuarded(
        context,
        () => c.include(path),
        failure: 'Could not include ${shortPath(path)}',
        success: (_) => 'Including ${shortPath(path)} again. Indexing it now…',
      );

  Future<bool?> _confirm({required String title, required String text, required String action}) => showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(title),
          content: Text(text, style: const TextStyle(color: C.text3)),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(action)),
          ],
        ),
      );

  Future<String?> _askPath({String title = 'Add a folder', String action = 'Add'}) {
    final ctrl = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          style: monoStyle(size: 14, color: C.text),
          decoration: const InputDecoration(hintText: '~/Pictures', border: OutlineInputBorder()),
          onSubmitted: (v) => Navigator.pop(ctx, v.trim()),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, ctrl.text.trim()), child: Text(action)),
        ],
      ),
    );
  }
}
