import 'package:flutter/material.dart';

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
