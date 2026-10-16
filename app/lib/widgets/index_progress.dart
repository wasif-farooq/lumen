import 'package:flutter/material.dart';

import '../theme.dart';
import 'common.dart';

/// The passes an index run goes through, in order (names match the server's events).
const indexPhases = [
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
        if (running) ..._running(p) else ..._finished(p),
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

  List<(String, String, String)> get _phases =>
      [for (final ph in indexPhases) if (widget.enabled.isEmpty || widget.enabled.contains(ph.$1)) ph];

  List<Widget> _running(Map<String, dynamic> p) {
    final paused = p['paused'] == true, pausing = p['pausing'] == true;
    final phase = p['phase'] as String?;
    final phases = _phases;
    final at = phases.indexWhere((ph) => ph.$1 == phase);
    final done = (p['done'] ?? 0) as int, total = (p['total'] ?? 0) as int;
    final title = phase == null ? 'Starting…' : indexPhases.firstWhere((ph) => ph.$1 == phase, orElse: () => (phase, phase, phase)).$3;
    final eta = p['eta'] as int?;
    final detail = switch (phase) {
      'scan' => (p['scanned'] ?? 0) > 0 ? '${_n(p['scanned'])} files checked' : 'Looking for new and changed files',
      'passages' => 'Making new text searchable',
      _ when total > 0 => '${_n(done)} of ${_n(total)}${eta != null && !paused ? ' · ${_eta(eta)}' : ''}',
      _ => 'Getting ready',
    };
    final recent = [for (final r in (p['recent'] as List? ?? [])) Map<String, dynamic>.from(r)];
    final color = paused || pausing ? C.muted : C.accent;
    return [
      Row(children: [
        Expanded(child: Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600))),
        _Chip(
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
      _Steps(phases: phases, current: at),
      if (p['path'] != null && phase != 'scan') ...[
        const SizedBox(height: 16),
        Text(paused ? 'LAST FILE' : 'NOW', style: const TextStyle(fontSize: 11.5, color: C.muted, letterSpacing: 0.8, fontWeight: FontWeight.w500)),
        const SizedBox(height: 8),
        _FileRow(path: p['path'], note: p['note'], kind: p['kind'], ext: p['ext'], current: !paused),
      ],
      if (recent.length > 1) ...[
        const SizedBox(height: 14),
        const Text('RECENTLY DONE', style: TextStyle(fontSize: 11.5, color: C.muted, letterSpacing: 0.8, fontWeight: FontWeight.w500)),
        const SizedBox(height: 4),
        for (final r in recent.skip(1).take(4)) _FileRow(path: r['path'], note: r['note'], kind: r['kind'], ext: r['ext'], compact: true),
      ],
    ];
  }

  List<Widget> _finished(Map<String, dynamic> p) {
    final s = Map<String, dynamic>.from(p['summary'] ?? widget.lastRun?['stats'] ?? {});
    final stopped = (p['lines'] as List? ?? []).any((l) => '$l'.startsWith('Stopped.'));
    final cap = s['captions'] is Map ? s['captions'] as Map : const {};
    final media = s['media'] is Map ? s['media'] as Map : const {};
    final visual = s['visual'] is Map ? s['visual'] as Map : const {};
    final failed = (cap['failed'] ?? 0) + (media['failed'] ?? 0) + (visual['failed'] ?? 0);
    final notes = [
      if (s['heavy_skipped'] != null) 'Images, video and speech skipped: ${s['heavy_skipped']}',
      for (final part in [cap, media, visual]) ...[if (part['error'] != null) '${part['error']}', if (part['stopped'] != null) '${part['stopped']}'],
    ];
    final seconds = (s['seconds'] ?? 0) + (cap['seconds'] ?? 0) + (media['seconds'] ?? 0) + (visual['seconds'] ?? 0);
    return [
      Row(children: [
        Expanded(child: Text(stopped ? 'Indexing stopped' : 'Last indexing run', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600))),
        if (stopped)
          const _Chip('Stopped', color: C.muted, icon: Icons.stop_rounded)
        else if (s.isNotEmpty)
          _Chip(failed > 0 ? 'Done with $failed failed' : 'Done', color: failed > 0 ? C.accent : C.green, icon: Icons.check_rounded),
      ]),
      const SizedBox(height: 4),
      Text(
        stopped
            ? 'Finished work is saved. The next run continues with the rest.'
            : s.isEmpty
                ? 'No summary for the last run.'
                : 'Checked ${_n(s['scanned'])} files${seconds > 0 ? ' in ${_duration(seconds.round())}' : ''}.',
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
            if (n is num && n > 0) _Count(value: _n(n), label: label),
          if (failed > 0) _Count(value: _n(failed), label: 'failed', color: C.red),
          if ([s['added'], s['updated'], s['removed'], cap['captioned'], media['media']].every((n) => n == null || n == 0))
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
}

String _n(dynamic n) {
  final s = '${n ?? 0}';
  return s.replaceAllMapped(RegExp(r'\B(?=(\d{3})+(?!\d))'), (_) => ',');
}

String _duration(int s) => s < 60 ? '${s}s' : (s < 3600 ? '${s ~/ 60}m ${s % 60}s' : '${s ~/ 3600}h ${s % 3600 ~/ 60}m');

String _eta(int s) => s < 60 ? 'under a minute left' : (s < 3600 ? 'about ${(s / 60).ceil()} min left' : 'about ${(s / 3600).toStringAsFixed(1)} h left');

class _Steps extends StatelessWidget {
  const _Steps({required this.phases, required this.current});
  final List<(String, String, String)> phases;
  final int current;
  @override
  Widget build(BuildContext context) => Wrap(spacing: 6, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
        for (final (i, ph) in phases.indexed) ...[
          if (i > 0) const Icon(Icons.chevron_right, size: 16, color: C.line2),
          Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(
              i < current ? Icons.check_circle : (i == current ? Icons.radio_button_checked : Icons.radio_button_unchecked),
              size: 16,
              color: i < current ? C.green : (i == current ? C.accent : C.muted),
            ),
            const SizedBox(width: 6),
            Text(ph.$2, style: TextStyle(fontSize: 13, color: i == current ? C.text : (i < current ? C.text3 : C.muted), fontWeight: i == current ? FontWeight.w500 : FontWeight.w400)),
          ]),
        ],
      ]);
}

class _FileRow extends StatelessWidget {
  const _FileRow({required this.path, this.note, this.kind, this.ext, this.current = false, this.compact = false});
  final String path;
  final String? note, kind, ext;
  final bool current, compact;
  @override
  Widget build(BuildContext context) {
    final name = path.split('/').last;
    final folder = shortPath(path.substring(0, path.length - name.length));
    final failed = (note ?? '').startsWith('failed');
    final row = Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (compact)
        Padding(
          padding: const EdgeInsets.only(top: 2),
          child: Icon(failed ? Icons.error_outline : Icons.check, size: 16, color: failed ? C.red : C.green),
        )
      else
        FileBadge(kind: kind ?? '', ext: ext ?? '', width: 36, height: 42),
      SizedBox(width: compact ? 10 : 12),
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text.rich(
            TextSpan(children: [
              TextSpan(text: name, style: const TextStyle(fontWeight: FontWeight.w500)),
              TextSpan(text: '  $folder', style: monoStyle(size: 12, color: C.muted)),
            ]),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: compact ? 13 : 14),
          ),
          if ((note ?? '').isNotEmpty)
            Text(
              note!,
              maxLines: compact ? 1 : 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 13, color: failed ? C.red : C.text3, height: 1.4),
            ),
        ]),
      ),
      if (current) ...[
        const SizedBox(width: 12),
        const Padding(padding: EdgeInsets.only(top: 4), child: SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: C.accent))),
      ],
    ]);
    return compact
        ? Padding(padding: const EdgeInsets.symmetric(vertical: 5), child: row)
        : Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: C.surface2, borderRadius: BorderRadius.circular(10)),
            child: row,
          );
  }
}

class _Chip extends StatelessWidget {
  const _Chip(this.label, {required this.color, this.icon});
  final String label;
  final Color color;
  final IconData? icon;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(20)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          if (icon != null) ...[Icon(icon, size: 14, color: color), const SizedBox(width: 4)] else ...[StatusDot(color: color), const SizedBox(width: 6)],
          Text(label, style: TextStyle(fontSize: 12.5, color: color, fontWeight: FontWeight.w500)),
        ]),
      );
}

class _Count extends StatelessWidget {
  const _Count({required this.value, required this.label, this.color = C.text});
  final String value, label;
  final Color color;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(color: C.surface2, borderRadius: BorderRadius.circular(10)),
        child: Text.rich(TextSpan(children: [
          TextSpan(text: value, style: TextStyle(fontWeight: FontWeight.w600, color: color)),
          TextSpan(text: ' $label', style: const TextStyle(color: C.text3)),
        ]), style: const TextStyle(fontSize: 13)),
      );
}
