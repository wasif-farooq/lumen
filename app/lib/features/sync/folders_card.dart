import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/cards.dart';
import 'sync_actions.dart';

/// The indexed folders, each with its file count and a menu (pause, clear, remove).
class FoldersCard extends StatelessWidget {
  const FoldersCard({super.key, required this.folders, required this.running, required this.actions});
  final List<Map<String, dynamic>> folders; // status['folders']: {path, files, paused}
  final bool running;
  final SyncActions actions;

  @override
  Widget build(BuildContext context) => SectionCard(
        title: 'Folders',
        trailing: OutlinedButton.icon(
          onPressed: running ? null : actions.addFolder,
          style: OutlinedButton.styleFrom(minimumSize: const Size(0, 36)),
          icon: const Icon(Icons.add, size: 16),
          label: const Text('Add folder'),
        ),
        child: Column(children: [
          for (final f in folders) _FolderRow(f: f, running: running, canRemove: folders.length > 1, actions: actions),
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
      );
}

class _FolderRow extends StatelessWidget {
  const _FolderRow({required this.f, required this.running, required this.canRemove, required this.actions});
  final Map<String, dynamic> f;
  final bool running, canRemove;
  final SyncActions actions;

  @override
  Widget build(BuildContext context) {
    final path = f['path'] as String;
    final paused = f['paused'] == true;
    final files = (f['files'] as num? ?? 0).toInt();
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(12, 4, 4, 4),
      constraints: const BoxConstraints(minHeight: 48),
      decoration: BoxDecoration(color: C.surface2, borderRadius: BorderRadius.circular(10)),
      child: Row(children: [
        const Icon(Icons.folder_outlined, size: 18, color: C.accent),
        const SizedBox(width: 12),
        Expanded(child: Text(shortPath(path), style: monoStyle(size: 13, color: paused ? C.text3 : C.text))),
        if (paused) ...[
          const Icon(Icons.pause_circle_outline, size: 15, color: C.blue),
          const SizedBox(width: 4),
          const Text('Paused', style: TextStyle(fontSize: 13, color: C.blue)),
          const SizedBox(width: 10),
        ],
        Text('${f['files']} files', style: const TextStyle(fontSize: 13, color: C.text3)),
        const SizedBox(width: 4),
        _FolderMenu(
          path: path,
          paused: paused,
          enabled: !running,
          canRemove: canRemove,
          onSync: () => actions.toggleFolderSync(path, paused),
          onClear: () => actions.clearFolder(path, files, paused),
          onRemove: () => actions.removeFolder(path, files),
        ),
      ]),
    );
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
