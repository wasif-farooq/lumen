import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/cards.dart';
import '../settings/setting_controls.dart';
import 'sync_actions.dart';

/// Files and folders kept out of the index, and the button to add one.
class ExclusionsCard extends StatelessWidget {
  const ExclusionsCard({super.key, required this.excluded, required this.gitignore, required this.running, required this.actions});
  final List<String> excluded;
  final bool gitignore, running;
  final SyncActions actions;

  @override
  Widget build(BuildContext context) => SectionCard(
        title: 'Kept out of the index',
        trailing: PopupMenuButton<bool>(
          enabled: !running,
          tooltip: 'Exclude a file or folder',
          onSelected: actions.exclude,
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
          SettingToggle(
            title: 'Respect .gitignore files',
            subtitle: 'In code projects, skip what git ignores: build output, caches, logs.',
            value: gitignore,
            onChanged: running ? null : actions.setGitignore,
          ),
          const SizedBox(height: 8),
          if (excluded.isEmpty)
            const Text('Nothing excluded. Files and folders you exclude are removed from search and skipped by later runs.',
                style: TextStyle(fontSize: 13, color: C.muted)),
          for (final e in excluded)
            Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.fromLTRB(12, 4, 4, 4),
              constraints: const BoxConstraints(minHeight: 44),
              decoration: BoxDecoration(color: C.surface2, borderRadius: BorderRadius.circular(10)),
              child: Row(children: [
                const Icon(Icons.block, size: 16, color: C.muted),
                const SizedBox(width: 12),
                Expanded(child: Text(shortPath(e), style: monoStyle(size: 13, color: C.text2), overflow: TextOverflow.ellipsis)),
                TextButton(onPressed: running ? null : () => actions.include(e), child: const Text('Include again')),
              ]),
            ),
        ]),
      );
}
