import '../../core/format.dart';

/// What the agent is doing, in words, for the status line above the message box:
/// "Searching your files · “tax” · PDF, DOCX".
String toolStatus(String name, Map<String, dynamic> args) {
  final (label, detail) = describeTool(name, args);
  return detail.isEmpty ? label : '$label · $detail';
}

/// What a tool call does ("Searching your files") and its details ("“tax” · PDF, DOCX", empty when none).
(String, String) describeTool(String name, Map<String, dynamic> args) {
  String arg(String key) => (args[key] ?? '').toString().trim();
  String quoted(String key) => arg(key).isEmpty ? '' : '“${arg(key)}”';
  // a path, or a result number from the last search
  String file(String key) => int.tryParse(arg(key)) != null ? 'result ${arg(key)}' : arg(key).split('/').last;
  final types = arg('ext').split(',').map((e) => e.trim().toUpperCase()).where((e) => e.isNotEmpty).join(', ');
  final at = (args['start_seconds'] as num? ?? 0) > 0 ? 'at ${clock((args['start_seconds'] as num).toDouble())}' : '';
  final folder = arg('folder').isEmpty ? '' : 'in ${arg('folder').split('/').last}';
  final (label, details) = switch (name) {
    'search_files' => (
        'Searching your files',
        [
          quoted('query'),
          types,
          if (arg('modified_after').isNotEmpty) 'since ${arg('modified_after')}',
          if (arg('modified_before').isNotEmpty) 'before ${arg('modified_before')}',
          folder,
        ]
      ),
    'find_in_files' => ('Searching inside your files', [quoted('question'), types, folder]),
    'read_file' => ('Reading', [file('target')]),
    'open_file' => ('Opening', [file('target'), at]),
    'show_in_folder' => ('Showing in its folder', [file('target')]),
    'list_dir' => ('Looking in', [file('path')]),
    'search_images' => ('Looking through your pictures', [quoted('description'), folder]),
    'find_similar_images' => ('Looking for similar pictures', ['like ${file('target')}']),
    'create_folder' => ('Preparing a new folder', [file('path')]),
    'create_file' => ('Preparing a new file', [file('path')]),
    'copy_file' => ('Preparing a copy', ['${file('source')} to ${file('destination')}']),
    'move_file' => ('Preparing a move', ['${file('source')} to ${file('destination')}']),
    _ => (_sentence(name), <String>[]),
  };
  return (label, details.where((d) => d.isNotEmpty).join(' · '));
}

/// "some_new_tool" → "Some new tool"
String _sentence(String name) {
  final words = name.replaceAll('_', ' ').trim();
  return words.isEmpty ? 'Working' : words[0].toUpperCase() + words.substring(1);
}
