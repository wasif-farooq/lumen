import 'package:flutter/material.dart';

import '../../core/models/json.dart';
import '../../shared/theme.dart';
import 'progress_parts.dart';

/// When no run is going: how the last one went (or that it stopped, or crashed).
List<Widget> summaryView(Map<String, dynamic> p, Map<String, dynamic>? lastRun) {
  final crash = p['error'] as String?;
  if (crash != null) return crashedView(crash);
  final s = mapOf(p['summary'] ?? lastRun?['stats']);
  final stopped = (p['lines'] as List? ?? []).any((l) => '$l'.startsWith('Stopped.'));
  final cap = mapOf(s['captions']), media = mapOf(s['media']), visual = mapOf(s['visual']);
  final failed = numOf(cap['failed']) + numOf(media['failed']) + numOf(visual['failed']);
  final notes = [
    if (s['heavy_skipped'] != null) 'Images, video and speech skipped: ${s['heavy_skipped']}',
    for (final part in [cap, media, visual]) ...[if (part['error'] != null) '${part['error']}', if (part['stopped'] != null) '${part['stopped']}'],
  ];
  final seconds = numOf(s['seconds']) + numOf(cap['seconds']) + numOf(media['seconds']) + numOf(visual['seconds']);
  return [
    Row(children: [
      Expanded(child: Text(stopped ? 'Indexing stopped' : 'Last indexing run', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600))),
      if (stopped)
        const StatusChip('Stopped', color: C.muted, icon: Icons.stop_rounded)
      else if (s.isNotEmpty)
        StatusChip(failed > 0 ? 'Done with $failed failed' : 'Done', color: failed > 0 ? C.accent : C.green, icon: Icons.check_rounded),
    ]),
    const SizedBox(height: 4),
    Text(
      stopped
          ? 'Finished work is saved. The next run continues with the rest.'
          : s.isEmpty
              ? 'No summary for the last run.'
              : 'Checked ${formatCount(s['scanned'])} files${seconds > 0 ? ' in ${formatDuration(seconds.round())}' : ''}.',
      style: const TextStyle(fontSize: 13, color: C.text3),
    ),
    if (s.isNotEmpty && !stopped) ...[
      const SizedBox(height: 14),
      Wrap(spacing: 8, runSpacing: 8, children: [
        for (final (n, label) in [
          (s['added'], 'added'),
          (s['updated'], 'updated'),
          (s['removed'], 'removed'),
          (cap['captioned'], 'images described'),
          (visual['images'], 'images fingerprinted'),
          (media['media'], media['media'] == 1 ? 'video or audio file' : 'video & audio files'),
        ])
          if (n is num && n > 0) CountChip(value: formatCount(n), label: label),
        if (failed > 0) CountChip(value: formatCount(failed), label: 'failed', color: C.red),
        if ([s['added'], s['updated'], s['removed'], cap['captioned'], media['media']].every((n) => numOf(n) == 0))
          const Text('Nothing new: the index is up to date.', style: TextStyle(fontSize: 13, color: C.muted)),
      ]),
    ],
    for (final n in notes)
      Padding(
        padding: const EdgeInsets.only(top: 10),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Icon(Icons.info_outline, size: 16, color: C.accent),
          const SizedBox(width: 8),
          Expanded(child: Text(n, style: const TextStyle(fontSize: 13, color: C.accent))),
        ]),
      ),
  ];
}

/// The indexer process ended on its own with an error: say so, and where the log is.
List<Widget> crashedView(String error) => [
      const Row(children: [
        Expanded(child: Text('Indexing stopped unexpectedly', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600))),
        StatusChip('Failed', color: C.red, icon: Icons.error_outline),
      ]),
      const SizedBox(height: 8),
      SelectableText(error, style: const TextStyle(fontSize: 13, color: C.text3)),
      const SizedBox(height: 4),
      const Text('Work finished before it stopped is saved. Re-index to try again.', style: TextStyle(fontSize: 13, color: C.muted)),
    ];
