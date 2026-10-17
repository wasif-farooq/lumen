// What Lumen is doing, as the status line above the message box says it: in words, not tool names.
import 'package:flutter_test/flutter_test.dart';
import 'package:lumen_app/features/chat/tool_status.dart';

void main() {
  test('every tool is described in words', () {
    expect(toolStatus('search_files', {'query': 'tax', 'ext': 'pdf,docx, xlsx'}), 'Searching your files · “tax” · PDF, DOCX, XLSX');
    expect(toolStatus('search_files', {'query': '', 'modified_after': '2026-01-01', 'folder': '/home/alex/Documents'}),
        'Searching your files · since 2026-01-01 · in Documents');
    expect(toolStatus('find_in_files', {'question': 'total amount'}), 'Searching inside your files · “total amount”');
    expect(toolStatus('read_file', {'target': '/home/alex/Documents/tax/tax-return-2025.pdf'}), 'Reading · tax-return-2025.pdf');
    expect(toolStatus('read_file', {'target': '2'}), 'Reading · result 2');
    expect(toolStatus('open_file', {'target': '1', 'start_seconds': 83}), 'Opening · result 1 · at 1:23');
    expect(toolStatus('show_in_folder', {'target': '/home/alex/Downloads/ticket.pdf'}), 'Showing in its folder · ticket.pdf');
    expect(toolStatus('list_dir', {'path': '/home/alex/Documents'}), 'Looking in · Documents');
    expect(toolStatus('search_images', {'description': 'a dog on the beach'}), 'Looking through your pictures · “a dog on the beach”');
    expect(toolStatus('find_similar_images', {'target': '3'}), 'Looking for similar pictures · like result 3');
    expect(toolStatus('create_folder', {'path': '/home/alex/Documents/Invoices'}), 'Preparing a new folder · Invoices');
    expect(toolStatus('create_file', {'path': '/home/alex/notes.txt', 'content': 'hi'}), 'Preparing a new file · notes.txt');
    expect(toolStatus('copy_file', {'source': '/a/b.pdf', 'destination': '/home/alex/Documents'}), 'Preparing a copy · b.pdf to Documents');
    expect(toolStatus('move_file', {'source': '1', 'destination': '/home/alex/Archive'}), 'Preparing a move · result 1 to Archive');
  });

  test('a tool the app does not know yet still reads as words', () {
    expect(toolStatus('summarize_folder', {}), 'Summarize folder');
    expect(toolStatus('', {}), 'Working');
  });
}
