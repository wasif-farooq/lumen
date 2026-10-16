import 'package:flutter/material.dart';

import '../../shared/theme.dart';

/// The index in numbers: files, with text, images described, videos, transcript lines.
class IndexStats extends StatelessWidget {
  const IndexStats({super.key, required this.index});
  final Map<String, dynamic> index;

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, c) {
        final cols = c.maxWidth > 900 ? 5 : (c.maxWidth > 560 ? 3 : 2);
        final w = (c.maxWidth - (cols - 1) * 12) / cols;
        return Wrap(spacing: 12, runSpacing: 12, children: [
          for (final (n, label) in [
            (index['files'], 'Files'),
            (index['with_text'], 'With searchable text'),
            (index['captioned'], 'Images & scans described'),
            (index['media_indexed'], 'Videos indexed'),
            (index['transcript_lines'], 'Transcript lines'),
          ])
            SizedBox(width: w, child: _Stat(value: '${n ?? '–'}', label: label)),
        ]);
      });
}

class _Stat extends StatelessWidget {
  const _Stat({required this.value, required this.label});
  final String value, label;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(color: C.surface, borderRadius: BorderRadius.circular(12), border: Border.all(color: C.line)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(value, style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w600)),
          Text(label, style: const TextStyle(fontSize: 13, color: C.text3), maxLines: 1, overflow: TextOverflow.ellipsis),
        ]),
      );
}
