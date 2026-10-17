// What the agent did, as the chat shows it: in words, not tool names.
import 'package:flutter_test/flutter_test.dart';
import 'package:lumen_app/features/chat/message_parts.dart';

String said(String name, [Map<String, dynamic> args = const {}]) {
  final (_, label, detail) = ToolChip.describe(name, args);
  return detail.isEmpty ? label : '$label · $detail';
}

void main() {
  test('every tool is described in words', () {
    expect(said('search_files', {'query': 'tax', 'ext': 'pdf,docx, xlsx'}), 'Searched your files · “tax” · PDF, DOCX, XLSX');
    expect(said('search_files', {'query': '', 'modified_after': '2026-01-01', 'folder': '/home/alex/Documents'}),
        'Searched your files · since 2026-01-01 · in Documents');
    expect(said('find_in_files', {'question': 'total amount'}), 'Searched inside your files · “total amount”');
    expect(said('read_file', {'target': '/home/alex/Documents/tax/tax-return-2025.pdf'}), 'Read · tax-return-2025.pdf');
    expect(said('read_file', {'target': '2'}), 'Read · result 2');
    expect(said('open_file', {'target': '1', 'start_seconds': 83}), 'Opened · result 1 · at 1:23');
    expect(said('show_in_folder', {'target': '/home/alex/Downloads/ticket.pdf'}), 'Showed in its folder · ticket.pdf');
    expect(said('list_dir', {'path': '/home/alex/Documents'}), 'Looked in · Documents');
    expect(said('search_images', {'description': 'a dog on the beach'}), 'Looked through your pictures · “a dog on the beach”');
    expect(said('find_similar_images', {'target': '3'}), 'Looked for similar pictures · like result 3');
    expect(said('create_folder', {'path': '/home/alex/Documents/Invoices'}), 'New folder · Invoices');
    expect(said('create_file', {'path': '/home/alex/notes.txt', 'content': 'hi'}), 'New file · notes.txt');
    expect(said('copy_file', {'source': '/a/b.pdf', 'destination': '/home/alex/Documents'}), 'Copy · b.pdf to Documents');
    expect(said('move_file', {'source': '1', 'destination': '/home/alex/Archive'}), 'Move · result 1 to Archive');
  });

  test('a tool the app does not know yet still reads as words', () {
    expect(said('summarize_folder'), 'Summarize folder');
    expect(said(''), 'Worked');
  });
}
