import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/errors/run_guarded.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/markdown.dart';
import 'planner_controller.dart';
import 'planner_parts.dart';

/// Notes: the list (with search) and the open note (Markdown, with a preview).
class NotesTab extends StatelessWidget {
  const NotesTab({super.key, required this.c, this.compact = false});
  final PlannerController c;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final list = _NoteList(c: c);
    if (compact) return c.note == null ? list : _NoteEditor(key: ValueKey(c.note!.name), c: c);
    return Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      SizedBox(width: 300, child: list),
      const VerticalDivider(width: 1, color: C.line),
      Expanded(
        child: c.note == null
            ? const Empty(icon: Icons.sticky_note_2_outlined, text: 'Pick a note, or make a new one.')
            : _NoteEditor(key: ValueKey(c.note!.name + c.note!.updated), c: c),
      ),
    ]);
  }
}

class _NoteList extends StatelessWidget {
  const _NoteList({required this.c});
  final PlannerController c;

  Future<void> _new(BuildContext context) async {
    final title = await askText(context, 'New note', 'Title');
    if (title != null && context.mounted) await runGuarded(context, () => c.newNote(title), failure: 'Could not make the note');
  }

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Row(children: [
            Expanded(
              child: TextField(
                onChanged: (q) => unawaited(c.search(q)),
                decoration: const InputDecoration(hintText: 'Search notes', prefixIcon: Icon(Icons.search, size: 18), isDense: true),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filledTonal(tooltip: 'New note', onPressed: () => _new(context), icon: const Icon(Icons.add)),
          ]),
        ),
        Expanded(
          child: c.notes.isEmpty
              ? const Empty(icon: Icons.sticky_note_2_outlined, text: 'No notes yet. Say “note: …” in chat, or make one here.')
              : ListView(children: [
                  for (final n in c.notes)
                    ListTile(
                      selected: c.note?.name == n.name,
                      selectedTileColor: C.raised,
                      title: Text(n.title, maxLines: 1, overflow: TextOverflow.ellipsis),
                      subtitle: Text(n.preview, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(color: C.text3, fontSize: 12.5)),
                      trailing: Text(n.updated.split(' ').first, style: const TextStyle(color: C.muted, fontSize: 12)),
                      onTap: () => runGuarded(context, () => c.openNote(n.name), failure: 'Could not open the note'),
                    ),
                ]),
        ),
      ]);
}

class _NoteEditor extends StatefulWidget {
  const _NoteEditor({super.key, required this.c});
  final PlannerController c;

  @override
  State<_NoteEditor> createState() => _NoteEditorState();
}

class _NoteEditorState extends State<_NoteEditor> {
  late final _title = TextEditingController(text: widget.c.note!.title);
  late final _text = TextEditingController(text: widget.c.note!.text);
  bool preview = false;
  bool changed = false;

  @override
  void dispose() {
    _title.dispose();
    _text.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    await runGuarded(context, () => widget.c.saveNote(title: _title.text, text: _text.text), failure: 'Could not save the note');
    if (mounted) setState(() => changed = false);
  }

  Future<void> _trash() async {
    final action = await runGuarded(context, widget.c.trashNote, failure: 'Could not delete the note');
    if (action != null && mounted) showUndo(context, 'Note sent to the Trash', () => widget.c.undo(action));
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.c;
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          if (widget.c.note != null && MediaQuery.sizeOf(context).width < 700)
            IconButton(tooltip: 'Back', onPressed: c.closeNote, icon: const Icon(Icons.arrow_back)),
          Expanded(
            child: TextField(
              controller: _title,
              onChanged: (_) => setState(() => changed = true),
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
              decoration: const InputDecoration(border: InputBorder.none, hintText: 'Title'),
            ),
          ),
          IconButton(
            tooltip: preview ? 'Edit' : 'Preview',
            onPressed: () => setState(() => preview = !preview),
            icon: Icon(preview ? Icons.edit_outlined : Icons.visibility_outlined, size: 20),
          ),
          IconButton(tooltip: 'Delete note', onPressed: _trash, icon: const Icon(Icons.delete_outline, size: 20)),
          const SizedBox(width: 8),
          FilledButton(onPressed: changed ? _save : null, child: const Text('Save')),
        ]),
        Text(c.note!.path, style: monoStyle(size: 11.5, color: C.muted), maxLines: 1, overflow: TextOverflow.ellipsis),
        const SizedBox(height: 12),
        Expanded(
          child: preview
              ? SingleChildScrollView(child: MarkdownView(_text.text))
              : TextField(
                  controller: _text,
                  onChanged: (_) => setState(() => changed = true),
                  maxLines: null,
                  expands: true,
                  textAlignVertical: TextAlignVertical.top,
                  style: monoStyle(size: 14, color: C.text),
                  decoration: const InputDecoration(border: InputBorder.none, hintText: 'Write in Markdown…'),
                ),
        ),
      ]),
    );
  }
}
