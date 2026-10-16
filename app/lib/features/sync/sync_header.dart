import 'package:flutter/material.dart';

import '../../shared/theme.dart';
import 'sync_actions.dart';
import 'sync_controller.dart';

/// "Last run 5 minutes ago" and the run's buttons: Pause / Resume, Stop, Re-index now.
class SyncHeader extends StatelessWidget {
  const SyncHeader({super.key, required this.c, required this.embedded, required this.lastRunAt, required this.actions});
  final SyncController c;
  final bool embedded;
  final Object? lastRunAt;
  final SyncActions actions;

  @override
  Widget build(BuildContext context) {
    final running = c.running, paused = c.paused;
    return Wrap(alignment: WrapAlignment.spaceBetween, crossAxisAlignment: WrapCrossAlignment.center, runSpacing: 12, children: [
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (!embedded) const Text('Sync', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
        Text(
          running ? (paused ? 'Indexing paused' : 'Indexing now…') : (lastRunAt == null ? 'Not indexed from the app yet' : 'Last run ${ago(lastRunAt)}'),
          style: const TextStyle(color: C.text3),
        ),
      ]),
      Row(mainAxisSize: MainAxisSize.min, children: [
        if (running) ...[
          OutlinedButton.icon(
            onPressed: c.pauseBusy || c.stopping ? null : actions.togglePause,
            icon: Icon(paused ? Icons.play_arrow_rounded : Icons.pause_rounded, size: 18),
            label: Text(paused ? 'Resume' : 'Pause'),
          ),
          const SizedBox(width: 8),
          OutlinedButton.icon(
            onPressed: c.stopping ? null : actions.stop,
            icon: const Icon(Icons.stop_rounded, size: 18),
            label: Text(c.stopping ? 'Stopping…' : 'Stop'),
          ),
          const SizedBox(width: 8),
        ],
        FilledButton.icon(
          onPressed: running ? null : actions.reindex,
          icon: running
              ? (paused
                  ? const Icon(Icons.pause_rounded, size: 18)
                  : const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: C.text3)))
              : const Icon(Icons.refresh, size: 18),
          label: Text(running ? (paused ? 'Paused' : 'Indexing…') : 'Re-index now'),
        ),
      ]),
    ]);
  }

  /// Seconds since 1970 -> "5 minutes ago".
  static String ago(Object? at) {
    if (at is! num) return '';
    final mins = (DateTime.now().millisecondsSinceEpoch / 1000 - at) ~/ 60;
    if (mins < 1) return 'just now';
    if (mins < 60) return '$mins minutes ago';
    if (mins < 60 * 24) return '${mins ~/ 60} hours ago';
    return '${mins ~/ (60 * 24)} days ago';
  }
}
