import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../core/errors/errors.dart';
import '../../shared/theme.dart';
import '../chat/message_parts.dart';
import 'planner_parts.dart';

/// Chat results of notes, to-dos and reminders ("Saved the note…", "Reminder: … every week"),
/// each with Undo. Null for other events.
Widget? plannerCard(ChatEvent e, AppState s) {
  final d = e.data;
  Map<String, dynamic> m(String k) => Map<String, dynamic>.from(d[k] as Map? ?? const {});
  switch (e.type) {
    case 'note_saved':
      final id = d['action_id'] as String?;
      return _Card(
        icon: Icons.sticky_note_2_outlined,
        text: '${d['added_to'] == true ? 'Added to' : 'Saved'} the note “${d['title']}”',
        undo: id == null ? null : () => s.undo(id),
      );
    case 'todo_added':
      final t = Todo.fromJson(m('todo'));
      return _Card(
        icon: Icons.add_task,
        text: 'Added “${t.text}” to ${t.list}${t.due != null ? ' · due ${shortTime(t.due!)}' : ''}',
        undo: () => s.api.deleteTodo(t.id),
      );
    case 'todo_done':
      final t = Todo.fromJson(m('todo'));
      return _Card(icon: Icons.check_circle_outline, text: 'Done: “${t.text}”', undo: () => s.api.changeTodo(t.id, done: false));
    case 'reminder_set':
      final r = Reminder.fromJson(m('reminder'));
      return _Card(icon: r.repeat == 'none' ? Icons.alarm : Icons.repeat, text: 'Reminder: ${r.text} · ${r.when}',
          undo: () => s.api.cancelReminder(r.id));
    case 'reminder_cancelled':
      final r = Reminder.fromJson(m('reminder'));
      return _Card(icon: Icons.alarm_off, text: 'Cancelled the reminder “${r.text}”', undo: () => s.api.restoreReminder(r.id));
    case 'reminder': // said on an open voice chat when it went off
      return _Card(icon: Icons.alarm, text: e.text);
    case 'todos':
      return _TodoList(todos: [for (final t in d['todos'] as List? ?? const []) Todo.fromJson(Map<String, dynamic>.from(t as Map))],
          reminders: [for (final r in d['reminders'] as List? ?? const []) Reminder.fromJson(Map<String, dynamic>.from(r as Map))]);
  }
  return null;
}

class _Card extends StatefulWidget {
  const _Card({required this.icon, required this.text, this.undo});
  final IconData icon;
  final String text;
  final Future<Object?> Function()? undo;

  @override
  State<_Card> createState() => _CardState();
}

class _CardState extends State<_Card> {
  bool undone = false;

  Future<void> _undo() async {
    try {
      await widget.undo!();
      if (mounted) setState(() => undone = true);
    } on Object catch (e, st) {
      logUnexpected('planner undo', e, st);
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not undo: ${userMessage(e)}')));
    }
  }

  @override
  Widget build(BuildContext context) => StatusRow(
        icon: undone ? Icons.undo : widget.icon,
        color: undone ? C.blue : C.green,
        text: undone ? 'Undone. ${widget.text}' : widget.text,
        trailing: widget.undo == null || undone
            ? null
            : TextButton.icon(onPressed: _undo, icon: const Icon(Icons.undo, size: 16), label: const Text('Undo')),
      );
}

/// "What do I have to do?": the open to-dos, numbered as the agent numbered them, and reminders.
class _TodoList extends StatelessWidget {
  const _TodoList({required this.todos, required this.reminders});
  final List<Todo> todos;
  final List<Reminder> reminders;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(color: C.surface, borderRadius: BorderRadius.circular(12), border: Border.all(color: C.line2)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (todos.isEmpty && reminders.isEmpty) const Text('Nothing to do, and no reminders.', style: TextStyle(color: C.text3)),
          for (final (i, t) in todos.indexed)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(children: [
                SizedBox(width: 24, child: Text('${i + 1}.', style: const TextStyle(color: C.muted))),
                PriorityDot(t.priority),
                const SizedBox(width: 8),
                Expanded(child: Text(t.text)),
                Text(t.list, style: const TextStyle(color: C.muted, fontSize: 12.5)),
                if (t.due != null) ...[const SizedBox(width: 8), DueChip(t.due!)],
              ]),
            ),
          if (reminders.isNotEmpty) ...[
            if (todos.isNotEmpty) const Divider(color: C.line, height: 18),
            for (final r in reminders)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(children: [
                  Icon(r.repeat == 'none' ? Icons.alarm : Icons.repeat, size: 16, color: C.accent),
                  const SizedBox(width: 8),
                  Expanded(child: Text(r.text)),
                  Text(r.when, style: const TextStyle(color: C.text3, fontSize: 12.5)),
                ]),
              ),
          ],
        ]),
      );
}
