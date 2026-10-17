/// Notes, to-do lists, to-dos and reminders, as the server sends them.
library;

DateTime? _time(Object? seconds) =>
    seconds is num ? DateTime.fromMillisecondsSinceEpoch((seconds * 1000).round()) : null;

/// A note in the list: no text, a preview.
class NoteSummary {
  final String name; // the file, relative to the notes folder (the note's id)
  final String title;
  final List<String> tags;
  final String updated;
  final String preview;

  NoteSummary.fromJson(Map<String, dynamic> j)
      : name = j['name'] as String,
        title = j['title'] as String? ?? '',
        tags = [for (final t in j['tags'] as List? ?? const []) '$t'],
        updated = j['updated'] as String? ?? '',
        preview = j['preview'] as String? ?? '';
}

class Note {
  final String name;
  final String path;
  final String title;
  final String text;
  final List<String> tags;
  final String updated;
  final String? actionId; // undo the change that made this version

  Note.fromJson(Map<String, dynamic> j)
      : name = j['name'] as String,
        path = j['path'] as String? ?? '',
        title = j['title'] as String? ?? '',
        text = j['text'] as String? ?? '',
        tags = [for (final t in j['tags'] as List? ?? const []) '$t'],
        updated = j['updated'] as String? ?? '',
        actionId = j['action_id'] as String?;
}

class TodoList {
  final int id;
  final String name;
  final int open; // to-dos not done yet

  TodoList.fromJson(Map<String, dynamic> j)
      : id = (j['id'] as num).toInt(),
        name = j['name'] as String? ?? '',
        open = (j['open'] as num? ?? 0).toInt();
}

class Todo {
  final int id;
  final int listId;
  final String list;
  final String text;
  final String notes;
  final int priority; // 0 none, 1 low, 2 medium, 3 high
  final DateTime? due;
  final DateTime? done;

  Todo.fromJson(Map<String, dynamic> j)
      : id = (j['id'] as num).toInt(),
        listId = (j['list_id'] as num? ?? 0).toInt(),
        list = j['list'] as String? ?? '',
        text = j['text'] as String? ?? '',
        notes = j['notes'] as String? ?? '',
        priority = (j['priority'] as num? ?? 0).toInt(),
        due = _time(j['due_at']),
        done = _time(j['done_at']);

  bool get isDone => done != null;
}

class Reminder {
  final int id;
  final String text;
  final DateTime at;
  final String repeat; // none | daily | weekdays | weekly | monthly
  final DateTime? next;
  final bool active;
  final bool acknowledged;
  final String when; // "tomorrow at 17:00, every week"

  Reminder.fromJson(Map<String, dynamic> j)
      : id = (j['id'] as num).toInt(),
        text = j['text'] as String? ?? '',
        at = _time(j['at']) ?? DateTime.now(),
        repeat = j['repeat'] as String? ?? 'none',
        next = _time(j['next_at']),
        active = j['active'] == true,
        acknowledged = j['acknowledged'] != false,
        when = j['when'] as String? ?? '';
}
