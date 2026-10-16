import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';
import 'index_progress.dart';

/// 12345 -> "12,345"
String formatCount(dynamic n) {
  final s = '${n ?? 0}';
  return s.replaceAllMapped(RegExp(r'\B(?=(\d{3})+(?!\d))'), (_) => ',');
}

String formatDuration(int s) => s < 60 ? '${s}s' : (s < 3600 ? '${s ~/ 60}m ${s % 60}s' : '${s ~/ 3600}h ${s % 3600 ~/ 60}m');

String formatEta(int s) => s < 60 ? 'under a minute left' : (s < 3600 ? 'about ${(s / 60).ceil()} min left' : 'about ${(s / 3600).toStringAsFixed(1)} h left');

class PhaseSteps extends StatelessWidget {
  const PhaseSteps({super.key, required this.phases, required this.current});
  final List<IndexPhase> phases;
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

class ProgressFileRow extends StatelessWidget {
  const ProgressFileRow({super.key, required this.path, this.note, this.kind, this.ext, this.current = false, this.compact = false});
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

class StatusChip extends StatelessWidget {
  const StatusChip(this.label, {super.key, required this.color, this.icon});
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

class CountChip extends StatelessWidget {
  const CountChip({super.key, required this.value, required this.label, this.color = C.text});
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
