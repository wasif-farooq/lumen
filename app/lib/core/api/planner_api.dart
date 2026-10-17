import '../models/json.dart';
import '../models/planner.dart';
import 'api_client.dart';

/// Notes (Markdown files in the notes folder), to-do lists, to-dos and reminders.
mixin PlannerApi on ApiClient {
  // ---------- notes ----------
  Future<List<NoteSummary>> notes([String query = '']) async =>
      [for (final n in listOf(await getJson('/api/notes', query.isEmpty ? null : {'q': query}))) NoteSummary.fromJson(n)];
  Future<Note> note(String name) async => Note.fromJson(mapOf(await getJson('/api/notes/${_file(name)}')));
  Future<Note> newNote(String title, String text) async =>
      Note.fromJson(mapOf(await sendJson('POST', '/api/notes', {'title': title, 'text': text})));
  Future<Note> saveNote(String name, {String? title, String? text}) async => Note.fromJson(mapOf(await sendJson(
      'PUT', '/api/notes/${_file(name)}', {'title': ?title, 'text': ?text})));

  /// To the Trash; returns the change's id (undo with ChatsApi.undo).
  Future<String?> trashNote(String name) async =>
      mapOf(await sendJson('DELETE', '/api/notes/${_file(name)}'))['action_id'] as String?;

  // ---------- lists and to-dos ----------
  Future<List<TodoList>> lists() async => [for (final l in listOf(await getJson('/api/lists'))) TodoList.fromJson(l)];
  Future<TodoList> newList(String name) async => TodoList.fromJson(mapOf(await sendJson('POST', '/api/lists', {'name': name})));
  Future<void> renameList(int id, String name) => sendJson('PATCH', '/api/lists/$id', {'name': name});
  Future<void> deleteList(int id) => sendJson('DELETE', '/api/lists/$id');

  Future<List<Todo>> todos({int? listId, bool done = false}) async => [
        for (final t in listOf(await getJson('/api/todos', {'done': '$done', if (listId != null) 'list_id': '$listId'})))
          Todo.fromJson(t)
      ];
  Future<Todo> newTodo(String text, {int? listId, String? due, int priority = 0}) async => Todo.fromJson(mapOf(
      await sendJson('POST', '/api/todos', {'text': text, 'list_id': ?listId, 'due': ?due, 'priority': priority})));

  /// Change a to-do: only the fields given (dueAt: clear it with [clearDue]).
  Future<Todo> changeTodo(int id,
          {String? text, bool? done, int? priority, int? position, int? listId, DateTime? dueAt, bool clearDue = false}) async =>
      Todo.fromJson(mapOf(await sendJson('PATCH', '/api/todos/$id', {
        'text': ?text,
        'done': ?done,
        'priority': ?priority,
        'position': ?position,
        'list_id': ?listId,
        if (dueAt != null) 'due_at': dueAt.millisecondsSinceEpoch / 1000,
        if (clearDue) 'due_at': null,
      })));
  Future<void> deleteTodo(int id) => sendJson('DELETE', '/api/todos/$id');

  // ---------- reminders ----------
  Future<List<Reminder>> reminders() async => [for (final r in listOf(await getJson('/api/reminders'))) Reminder.fromJson(r)];

  /// Reminders that went off and wait for the user (the banner).
  Future<List<Reminder>> dueReminders() async =>
      [for (final r in listOf(await getJson('/api/reminders/due'))) Reminder.fromJson(r)];

  /// At a time, or from plain words ("tomorrow at 5pm").
  Future<Reminder> newReminder(String text, {DateTime? at, String? when, String repeat = 'none'}) async =>
      Reminder.fromJson(mapOf(await sendJson('POST', '/api/reminders', {
        'text': text,
        if (at != null) 'at': at.millisecondsSinceEpoch / 1000,
        'when': ?when,
        'repeat': repeat,
      })));
  Future<void> cancelReminder(int id) => sendJson('DELETE', '/api/reminders/$id');
  Future<void> restoreReminder(int id) => sendJson('POST', '/api/reminders/$id/restore');
  Future<void> snoozeReminder(int id, {int minutes = 10}) =>
      sendJson('POST', '/api/reminders/$id/snooze', {'minutes': minutes});
  Future<void> acknowledgeReminder(int id) => sendJson('POST', '/api/reminders/$id/ack');

  /// A note's name in a URL ("Old idea.md", "trips/Hunza.md").
  String _file(String name) => name.split('/').map(Uri.encodeComponent).join('/');
}
