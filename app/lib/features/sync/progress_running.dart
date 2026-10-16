import 'package:flutter/material.dart';

import '../../core/models/json.dart';
import '../../shared/theme.dart';
import 'index_progress.dart';
import 'progress_parts.dart';

/// A run in progress: step, progress bar, the file being worked on, recently finished files.
List<Widget> runningView(Map<String, dynamic> p, List<IndexPhase> phases) {
  final paused = p['paused'] == true, pausing = p['pausing'] == true;
  final phase = p['phase'] as String?;
  final at = phases.indexWhere((ph) => ph.$1 == phase);
  final done = (p['done'] ?? 0) as int, total = (p['total'] ?? 0) as int;
  final title = phase == null ? 'Starting…' : indexPhases.firstWhere((ph) => ph.$1 == phase, orElse: () => (phase, phase, phase)).$3;
  final eta = p['eta'] as int?;
  final detail = switch (phase) {
    'scan' => numOf(p['scanned']) > 0 ? '${formatCount(p['scanned'])} files checked' : 'Looking for new and changed files',
    'passages' => 'Making new text searchable',
    _ when total > 0 => '${formatCount(done)} of ${formatCount(total)}${eta != null && !paused ? ' · ${formatEta(eta)}' : ''}',
    _ => 'Getting ready',
  };
  final recent = listOf(p['recent']);
  final color = paused || pausing ? C.muted : C.accent;
  return [
    Row(children: [
      Expanded(child: Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600))),
      StatusChip(
        paused ? 'Paused' : (pausing ? 'Pausing…' : 'Running'),
        color: paused || pausing ? C.blue : C.accent,
        icon: paused ? Icons.pause_rounded : null,
      ),
    ]),
    const SizedBox(height: 4),
    Text(
      paused
          ? 'Paused. Everything finished so far is saved and searchable.'
          : pausing
              ? 'Pausing after the current file…'
              : '${at >= 0 ? 'Step ${at + 1} of ${phases.length} · ' : ''}$detail',
      style: const TextStyle(fontSize: 13, color: C.text3),
    ),
    const SizedBox(height: 14),
    ClipRRect(
      borderRadius: BorderRadius.circular(4),
      child: LinearProgressIndicator(
        value: total > 0 && phase != 'scan' ? done / total : (paused ? 0 : null),
        minHeight: 6,
        color: color,
        backgroundColor: C.surface2,
      ),
    ),
    const SizedBox(height: 14),
    PhaseSteps(phases: phases, current: at),
    if (p['path'] != null && phase != 'scan') ...[
      const SizedBox(height: 16),
      Text(paused ? 'LAST FILE' : 'NOW', style: const TextStyle(fontSize: 11.5, color: C.muted, letterSpacing: 0.8, fontWeight: FontWeight.w500)),
      const SizedBox(height: 8),
      ProgressFileRow(path: p['path'], note: p['note'], kind: p['kind'], ext: p['ext'], current: !paused),
    ],
    if (recent.length > 1) ...[
      const SizedBox(height: 14),
      const Text('RECENTLY DONE', style: TextStyle(fontSize: 11.5, color: C.muted, letterSpacing: 0.8, fontWeight: FontWeight.w500)),
      const SizedBox(height: 4),
      for (final r in recent.skip(1).take(4)) ProgressFileRow(path: r['path'], note: r['note'], kind: r['kind'], ext: r['ext'], compact: true),
    ],
  ];
}
