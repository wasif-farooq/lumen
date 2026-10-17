import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/app_state.dart';

/// What the Notes & to-dos screen shows and does. Actions throw [ApiError]; the screen shows it
/// (runGuarded).
class PlannerController extends ChangeNotifier {
  PlannerController(this.app);

  final AppState app;
  Api get api => app.api;
  bool _disposed = false;

  // notes
  List<NoteSummary> notes = [];
  String query = '';
  Note? note; // the open note

  // to-dos
  List<TodoList> lists = [];
  int? listId; // the list shown
  List<Todo> todos = [];
  List<Todo> done = [];

  // reminders
  List<Reminder> reminders = [];

  Object? loadError;

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  void _changed() {
    if (!_disposed) notifyListeners();
  }

  TodoList? get list => lists.where((l) => l.id == listId).firstOrNull;

  void start() => unawaited(load());

  Future<void> load() async {
    try {
      final (n, l, r) = await (api.notes(query), api.lists(), api.reminders()).wait;
      notes = n;
      lists = l;
      reminders = r;
      listId = lists.any((x) => x.id == listId) ? listId : lists.firstOrNull?.id;
      await _loadTodos();
      loadError = null;
    } on Object catch (e) {
      loadError = e;
    }
    _changed();
  }

  Future<void> _loadTodos() async {
    if (listId == null) return;
    final (open, finished) = await (api.todos(listId: listId), api.todos(listId: listId, done: true)).wait;
    todos = open;
    done = finished;
  }

  // ---------- notes ----------

  Future<void> search(String q) async {
    query = q;
    notes = await api.notes(q);
    _changed();
  }

  Future<void> openNote(String name) async {
    note = await api.note(name);
    _changed();
  }

  void closeNote() {
    note = null;
    _changed();
  }

  Future<void> newNote(String title) async {
    note = await api.newNote(title, '');
    notes = await api.notes(query);
    _changed();
  }

  Future<void> saveNote({String? title, String? text}) async {
    final current = note;
    if (current == null) return;
    note = await api.saveNote(current.name, title: title, text: text);
    notes = await api.notes(query);
    _changed();
  }

  /// To the Trash; returns the change's id for Undo.
  Future<String?> trashNote() async {
    final current = note;
    if (current == null) return null;
    final action = await api.trashNote(current.name);
    note = null;
    notes = await api.notes(query);
    _changed();
    return action;
  }

  Future<void> undo(String actionId) async {
    await api.undo(actionId, null);
    await load();
  }

  // ---------- to-dos ----------

  Future<void> showList(int id) async {
    listId = id;
    await _loadTodos();
    _changed();
  }

  Future<void> newList(String name) async {
    final l = await api.newList(name);
    listId = l.id;
    await load();
  }

  Future<void> deleteList() async {
    final id = listId;
    if (id == null) return;
    await api.deleteList(id);
    listId = null;
    await load();
  }

  /// [due]: plain words ("Friday 5pm"), checked by the server.
  Future<void> addTodo(String text, {String? due}) async {
    await api.newTodo(text, listId: listId, due: due);
    await _refreshTodos();
  }

  Future<void> setDone(Todo t, bool value) async {
    await api.changeTodo(t.id, done: value);
    await _refreshTodos();
  }

  Future<void> setPriority(Todo t, int priority) async {
    await api.changeTodo(t.id, priority: priority);
    await _refreshTodos();
  }

  Future<void> deleteTodo(Todo t) async {
    await api.deleteTodo(t.id);
    await _refreshTodos();
  }

  /// Move a to-do from one place to another ([to] counted without it, as onReorderItem gives it).
  Future<void> reorder(int from, int to) async {
    if (from < 0 || from >= todos.length) return;
    final moved = todos.removeAt(from);
    final at = to.clamp(0, todos.length);
    todos.insert(at, moved);
    _changed(); // at once; the server agrees a moment later
    await api.changeTodo(moved.id, position: at);
    await _refreshTodos();
  }

  Future<void> _refreshTodos() async {
    lists = await api.lists();
    await _loadTodos();
    _changed();
  }

  // ---------- reminders ----------

  Future<void> addReminder(String text, DateTime at, String repeat) async {
    await api.newReminder(text, at: at, repeat: repeat);
    reminders = await api.reminders();
    _changed();
  }

  Future<void> cancelReminder(Reminder r) async {
    await api.cancelReminder(r.id);
    reminders = await api.reminders();
    _changed();
  }

  Future<void> restoreReminder(Reminder r) async {
    await api.restoreReminder(r.id);
    reminders = await api.reminders();
    _changed();
  }
}
