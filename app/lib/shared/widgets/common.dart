import 'package:flutter/material.dart';

import '../../core/api/api.dart';
import '../theme.dart';
import '../../core/format.dart';

/// Colored file-type tile (PDF, IMG, VID…).
class FileBadge extends StatelessWidget {
  const FileBadge({super.key, required this.kind, required this.ext, this.width = 40, this.height = 48});
  final String kind, ext;
  final double width, height;

  @override
  Widget build(BuildContext context) {
    final (bg, fg, label) = switch (kind) {
      'pdf' => (const Color(0xFF3A2326), const Color(0xFFFF9C93), 'PDF'),
      'image' => (const Color(0xFF1F2E3A), const Color(0xFF8DC8FF), 'IMG'),
      'video' => (const Color(0xFF2C2440), const Color(0xFFC3A8FF), 'VID'),
      'audio' => (const Color(0xFF2C2440), const Color(0xFFC3A8FF), 'AUD'),
      'doc' => (const Color(0xFF1E2A3E), const Color(0xFF9DBEFF), 'DOC'),
      'sheet' => (const Color(0xFF1C3127), const Color(0xFF8FDCB0), 'XLS'),
      _ => (C.surface2, C.text3, ext.isEmpty ? 'FILE' : ext.toUpperCase().substring(0, ext.length.clamp(0, 4))),
    };
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(6)),
      alignment: Alignment.bottomCenter,
      padding: const EdgeInsets.only(bottom: 6),
      child: Text(label, style: TextStyle(color: fg, fontSize: 10.5, fontWeight: FontWeight.w600)),
    );
  }
}

/// Text with search matches (server marks them with [brackets]) highlighted.
class Highlighted extends StatelessWidget {
  const Highlighted(this.text, {super.key, this.style, this.maxLines});
  final String text;
  final TextStyle? style;
  final int? maxLines;

  @override
  Widget build(BuildContext context) {
    final spans = <TextSpan>[];
    final re = RegExp(r'\[([^\]]+)\]');
    var last = 0;
    for (final m in re.allMatches(text)) {
      if (m.start > last) spans.add(TextSpan(text: text.substring(last, m.start)));
      spans.add(TextSpan(
        text: m.group(1),
        style: const TextStyle(color: C.markFg, backgroundColor: C.markBg),
      ));
      last = m.end;
    }
    if (last < text.length) spans.add(TextSpan(text: text.substring(last)));
    return Text.rich(
      TextSpan(children: spans),
      style: style ?? const TextStyle(fontSize: 13, color: Color(0xFFC3CAD1)),
      maxLines: maxLines,
      overflow: maxLines == null ? null : TextOverflow.ellipsis,
    );
  }
}

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

class StatusDot extends StatelessWidget {
  const StatusDot({super.key, this.color = C.green, this.size = 8});
  final Color color;
  final double size;
  @override
  Widget build(BuildContext context) =>
      Container(width: size, height: size, decoration: BoxDecoration(color: color, shape: BoxShape.circle));
}

class Logo extends StatelessWidget {
  const Logo({super.key, this.size = 28});
  final double size;
  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        decoration: BoxDecoration(color: C.accent, borderRadius: BorderRadius.circular(size / 4)),
        padding: EdgeInsets.all(size * 0.26),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            FractionallySizedBox(widthFactor: 0.6, child: Container(height: 2, color: C.onAccent)),
            Container(height: 2, color: C.onAccent),
            FractionallySizedBox(widthFactor: 0.75, child: Container(height: 2, color: C.onAccent)),
          ],
        ),
      );
}

/// Image from the API (thumbnails), sending the pairing token when there is one.
class ApiImage extends StatelessWidget {
  const ApiImage({super.key, required this.api, required this.path, this.w = 480, this.t, this.fit = BoxFit.cover});
  final Api api;
  final String path;
  final int w;
  final double? t;
  final BoxFit fit;

  @override
  Widget build(BuildContext context) => Image.network(
        api.thumbUrl(path, w: w, t: t),
        headers: api.headers,
        fit: fit,
        gaplessPlayback: true,
        errorBuilder: (_, _, _) => const ColoredBox(color: C.surface2),
        loadingBuilder: (c, child, progress) => progress == null ? child : const ColoredBox(color: C.surface2),
      );
}
