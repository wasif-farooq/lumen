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

/// What the agent did, in words: "Searched your files · “tax” · PDF, DOCX".
class ToolChip extends StatelessWidget {
  const ToolChip({super.key, required this.name, required this.args});
  final String name;
  final Map<String, dynamic> args;

  /// The icon, what was done, and its details (empty when there are none).
  static (IconData, String, String) describe(String name, Map<String, dynamic> args) {
    String arg(String key) => (args[key] ?? '').toString().trim();
    String quoted(String key) => arg(key).isEmpty ? '' : '“${arg(key)}”';
    // a path, or a result number from the last search
    String file(String key) => int.tryParse(arg(key)) != null ? 'result ${arg(key)}' : arg(key).split('/').last;
    final types = arg('ext').split(',').map((e) => e.trim().toUpperCase()).where((e) => e.isNotEmpty).join(', ');
    final at = (args['start_seconds'] as num? ?? 0) > 0 ? 'at ${clock((args['start_seconds'] as num).toDouble())}' : '';
    final folder = arg('folder').isEmpty ? '' : 'in ${arg('folder').split('/').last}';
    final (icon, label, details) = switch (name) {
      'search_files' => (
          Icons.search,
          'Searched your files',
          [
            quoted('query'),
            types,
            if (arg('modified_after').isNotEmpty) 'since ${arg('modified_after')}',
            if (arg('modified_before').isNotEmpty) 'before ${arg('modified_before')}',
            folder,
          ]
        ),
      'find_in_files' => (Icons.manage_search, 'Searched inside your files', [quoted('question'), types, folder]),
      'read_file' => (Icons.article_outlined, 'Read', [file('target')]),
      'open_file' => (Icons.open_in_new, 'Opened', [file('target'), at]),
      'show_in_folder' => (Icons.folder_open_outlined, 'Showed in its folder', [file('target')]),
      'list_dir' => (Icons.folder_outlined, 'Looked in', [file('path')]),
      'search_images' => (Icons.image_search, 'Looked through your pictures', [quoted('description'), folder]),
      'find_similar_images' => (Icons.collections_outlined, 'Looked for similar pictures', ['like ${file('target')}']),
      'create_folder' => (Icons.create_new_folder_outlined, 'New folder', [file('path')]),
      'create_file' => (Icons.note_add_outlined, 'New file', [file('path')]),
      'copy_file' => (Icons.file_copy_outlined, 'Copy', ['${file('source')} to ${file('destination')}']),
      'move_file' => (Icons.drive_file_move_outlined, 'Move', ['${file('source')} to ${file('destination')}']),
      _ => (Icons.build_outlined, _sentence(name), <String>[]),
    };
    return (icon, label, details.where((d) => d.isNotEmpty).join(' · '));
  }

  /// "some_new_tool" → "Some new tool"
  static String _sentence(String name) {
    final words = name.replaceAll('_', ' ').trim();
    return words.isEmpty ? 'Worked' : words[0].toUpperCase() + words.substring(1);
  }

  @override
  Widget build(BuildContext context) {
    final (icon, label, detail) = describe(name, args);
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
          Text(label, style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w500, color: C.blue)),
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
