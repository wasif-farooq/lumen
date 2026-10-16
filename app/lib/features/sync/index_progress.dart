import 'package:flutter/material.dart';

import '../../shared/theme.dart';
import 'progress_running.dart';
import 'progress_summary.dart';

/// The passes an index run goes through, in order (names match the server's events).
typedef IndexPhase = (String id, String short, String title);

const List<IndexPhase> indexPhases = [
  ('scan', 'Files', 'Checking files'),
  ('captions', 'Images', 'Describing images & scans'),
  ('visual', 'Look-alikes', 'Fingerprinting images'),
  ('media', 'Video & audio', 'Describing video & audio'),
  ('passages', 'Finish', 'Finishing up'),
];

/// Live view of an index run: current step, progress bar, the file being worked on,
/// recently finished files and, folded away, the raw log. Shows the last run's summary when idle.
class IndexProgressCard extends StatefulWidget {
  const IndexProgressCard({super.key, required this.progress, this.lastRun, this.enabled = const {}});
  final Map<String, dynamic> progress;
  final Map<String, dynamic>? lastRun; // status['last_index']: {at, stats}
  final Set<String> enabled; // phases turned on in settings; empty = all

  @override
  State<IndexProgressCard> createState() => _IndexProgressCardState();
}

class _IndexProgressCardState extends State<IndexProgressCard> {
  bool _log = false;

  @override
  Widget build(BuildContext context) {
    final p = widget.progress;
    final running = p['running'] == true;
    final lines = (p['lines'] as List? ?? []).cast<String>();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(color: C.surface, borderRadius: BorderRadius.circular(14), border: Border.all(color: C.line)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (running) ...runningView(p, _phases) else ...summaryView(p, widget.lastRun),
        if (lines.isNotEmpty) ...[
          const SizedBox(height: 12),
          TextButton.icon(
            onPressed: () => setState(() => _log = !_log),
            style: TextButton.styleFrom(foregroundColor: C.muted, padding: const EdgeInsets.symmetric(horizontal: 8), minimumSize: const Size(0, 32)),
            icon: Icon(_log ? Icons.expand_less : Icons.expand_more, size: 18),
            label: Text(_log ? 'Hide technical log' : 'Show technical log', style: const TextStyle(fontSize: 13)),
          ),
          if (_log)
            Container(
              constraints: const BoxConstraints(maxHeight: 200),
              width: double.infinity,
              margin: const EdgeInsets.only(top: 6),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: C.bg, borderRadius: BorderRadius.circular(10)),
              child: SingleChildScrollView(reverse: true, child: SelectableText(lines.join('\n'), style: monoStyle(size: 12, color: C.text2))),
            ),
        ],
      ]),
    );
  }

  List<IndexPhase> get _phases =>
      [for (final ph in indexPhases) if (widget.enabled.isEmpty || widget.enabled.contains(ph.$1)) ph];
}
