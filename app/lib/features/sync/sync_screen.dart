import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/widgets/cards.dart';
import '../../shared/widgets/error_views.dart';
import 'exclusions_card.dart';
import 'folders_card.dart';
import 'index_progress.dart';
import 'index_stats.dart';
import 'sync_actions.dart';
import 'sync_controller.dart';
import 'sync_header.dart';

/// Sync: what is indexed and the live indexing run. Preferences live in SettingsScreen.
class IndexScreen extends StatefulWidget {
  const IndexScreen({super.key, required this.state, this.embedded = false});
  final AppState state;
  final bool embedded; // inside the Settings tabs: no page title

  @override
  State<IndexScreen> createState() => _IndexScreenState();
}

class _IndexScreenState extends State<IndexScreen> {
  late final c = SyncController(widget.state)..start();

  @override
  void dispose() {
    c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final actions = SyncActions(context, c);
    return ListenableBuilder(
      listenable: Listenable.merge([widget.state, c]),
      builder: (context, _) {
        final st = widget.state.status ?? {};
        final last = st['last_index'];
        final folders = [for (final f in st['folders'] as List? ?? const []) Map<String, dynamic>.from(f as Map)];
        return ListView(
          padding: EdgeInsets.fromLTRB(32, widget.embedded ? 20 : 28, 32, 40),
          children: [
            SyncHeader(c: c, embedded: widget.embedded, lastRunAt: last is Map ? last['at'] : null, actions: actions),
            if (c.loadError != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: ErrorCard(error: c.loadError!, title: "Couldn't load the sync settings", onRetry: c.load),
              ),
            const SizedBox(height: 24),
            IndexStats(index: Map<String, dynamic>.from(st['index'] as Map? ?? const {})),
            if (c.running || c.lines.isNotEmpty || last != null || c.progress?['error'] != null) ...[
              const SizedBox(height: 20),
              IndexProgressCard(
                progress: c.progress ?? const {},
                lastRun: last is Map ? Map<String, dynamic>.from(last) : null,
                enabled: c.enabledPhases,
              ),
            ],
            const SizedBox(height: 20),
            TwoColumns(children: [
              CardColumn(children: [FoldersCard(folders: folders, running: c.running, actions: actions)]),
              CardColumn(children: [ExclusionsCard(excluded: c.excluded, running: c.running, actions: actions)]),
            ]),
          ],
        );
      },
    );
  }
}
