import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../shared/theme.dart';

/// A change the agent wants to make: what, where, and Approve / Cancel.
class ApprovalCard extends StatelessWidget {
  const ApprovalCard({super.key, required this.plan, required this.pending, required this.answer, required this.busy, required this.onAnswer});
  final Map<String, dynamic> plan;
  final bool pending, busy;
  final bool? answer;
  final void Function(bool approved) onAnswer;

  @override
  Widget build(BuildContext context) {
    final op = plan['op'] as String? ?? '';
    final (icon, title) = switch (op) {
      'create_folder' => (Icons.create_new_folder_outlined, 'Create a folder'),
      'create_file' => (Icons.note_add_outlined, 'Create a file'),
      'copy' => (Icons.copy_all_outlined, 'Copy'),
      'move' => (Icons.drive_file_move_outline, (plan['summary'] ?? '').toString().startsWith('Rename') ? 'Rename' : 'Move'),
      _ => (Icons.edit_outlined, 'Change'),
    };
    final size = plan['size'] is int && op != 'create_folder' ? ' · ${humanSize(plan['size'])}' : '';
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: pending ? C.accentSoft : C.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: pending ? C.accent : C.line, width: pending ? 1.5 : 1),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(icon, size: 20, color: C.accent),
          const SizedBox(width: 10),
          Text('$title$size', style: const TextStyle(fontWeight: FontWeight.w600)),
          const Spacer(),
          if (!pending)
            Text(answer == true ? 'Approved' : (answer == false ? 'Cancelled' : ''), style: const TextStyle(fontSize: 12.5, color: C.muted)),
        ]),
        const SizedBox(height: 10),
        if (plan['src'] != null) PathLine(label: 'From', path: plan['src']),
        if (plan['dst'] != null) PathLine(label: plan['src'] != null ? 'To' : 'Path', path: plan['dst']),
        if ((plan['preview'] ?? '').toString().isNotEmpty) ...[
          const SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(color: C.bg, borderRadius: BorderRadius.circular(8)),
            child: Text(plan['preview'], style: monoStyle(size: 12, color: C.text2), maxLines: 8, overflow: TextOverflow.ellipsis),
          ),
        ],
        if (pending) ...[
          const SizedBox(height: 14),
          Row(children: [
            FilledButton(onPressed: busy ? null : () => onAnswer(true), child: const Text('Approve')),
            const SizedBox(width: 8),
            OutlinedButton(onPressed: busy ? null : () => onAnswer(false), child: const Text('Cancel')),
            const SizedBox(width: 12),
            const Expanded(child: Text('Never overwrites. You can undo it after.', style: TextStyle(fontSize: 12, color: C.muted))),
          ]),
        ],
      ]),
    );
  }
}

class PathLine extends StatelessWidget {
  const PathLine({super.key, required this.label, required this.path});
  final String label, path;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: 44, child: Text(label, style: const TextStyle(fontSize: 13, color: C.muted))),
          Expanded(child: SelectableText(shortPath(path), style: monoStyle(size: 12.5, color: C.text))),
        ]),
      );
}
