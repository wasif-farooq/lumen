import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../shared/theme.dart';

/// Minimal markdown for agent answers: **bold**, `code`, line breaks.
class AnswerText extends StatelessWidget {
  const AnswerText(this.text, {super.key, this.size = 14.5});
  final String text;
  final double size;

  @override
  Widget build(BuildContext context) {
    final spans = <InlineSpan>[];
    final re = RegExp(r'\*\*(.+?)\*\*|`([^`]+)`');
    final clean = text.replaceAll(RegExp(r'^#+\s*', multiLine: true), '').replaceAll(RegExp(r'^\s*[-*]\s+', multiLine: true), '• ');
    var last = 0;
    for (final m in re.allMatches(clean)) {
      if (m.start > last) spans.add(TextSpan(text: clean.substring(last, m.start)));
      if (m.group(1) != null) {
        spans.add(TextSpan(text: m.group(1), style: const TextStyle(fontWeight: FontWeight.w600)));
      } else {
        spans.add(TextSpan(text: m.group(2), style: monoStyle(size: size - 1.5, color: C.text2)));
      }
      last = m.end;
    }
    if (last < clean.length) spans.add(TextSpan(text: clean.substring(last)));
    return SelectableText.rich(TextSpan(children: spans), style: TextStyle(fontSize: size, height: 1.5, color: C.text));
  }
}

/// What the agent did: the tool and its main arguments.
class ToolChip extends StatelessWidget {
  const ToolChip({super.key, required this.name, required this.args});
  final String name;
  final Map<String, dynamic> args;

  @override
  Widget build(BuildContext context) {
    final icon = switch (name) {
      'search_files' => Icons.search,
      'open_file' => Icons.open_in_new,
      'read_file' => Icons.article_outlined,
      'show_in_folder' => Icons.folder_open_outlined,
      _ => Icons.build_outlined,
    };
    final detail = [
      if ((args['query'] ?? '').toString().isNotEmpty) '“${args['query']}”',
      if ((args['ext'] ?? '').toString().isNotEmpty) '${args['ext']}',
      if (args['modified_after'] != null && '${args['modified_after']}'.isNotEmpty) 'after ${args['modified_after']}',
      if (args['target'] != null) 'result ${args['target']}',
      if ((args['start_seconds'] ?? 0) != 0) 'at ${clock((args['start_seconds'] as num).toDouble())}',
    ].join(' · ');
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: C.toolBg,
          border: Border.all(color: C.toolLine),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 14, color: C.blue),
          const SizedBox(width: 8),
          Text(name, style: monoStyle(size: 12.5, color: C.blue)),
          if (detail.isNotEmpty) ...[
            const SizedBox(width: 8),
            Flexible(child: Text(detail, style: const TextStyle(fontSize: 12.5, color: C.muted), overflow: TextOverflow.ellipsis)),
          ],
        ]),
      ),
    );
  }
}

/// One line about an action: done, cancelled, failed or undone.
class StatusRow extends StatelessWidget {
  const StatusRow({super.key, required this.icon, required this.color, required this.text, this.trailing});
  final IconData icon;
  final Color color;
  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Row(children: [
        Icon(icon, size: 16, color: color),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: const TextStyle(fontSize: 13, color: C.text2))),
        ?trailing,
      ]);
}
