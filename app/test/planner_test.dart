// Notes, to-dos and reminders in the app, against a fake server (made-up data, user "alex").
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumen_app/core/app_state.dart';
import 'package:lumen_app/features/planner/planner_screen.dart';
import 'package:lumen_app/features/shell/desktop_shell.dart';
import 'package:lumen_app/shared/theme.dart';

import 'helpers.dart';

final _at = DateTime.now().add(const Duration(days: 1)).copyWith(hour: 9, minute: 0, second: 0, millisecond: 0).millisecondsSinceEpoch / 1000;

/// A fake `lumen serve`: what it is asked is recorded in [calls].
class FakeServer {
  final calls = <String>[];
  List<Map<String, Object?>> due = [];

  late final client = MockClient((req) async {
    calls.add('${req.method} ${req.url.path}${req.body.isEmpty ? '' : ' ${req.body}'}');
    final Object body = switch ((req.method, req.url.path)) {
      ('GET', '/api/status') => jsonDecode(fixture('status')),
      ('GET', '/api/notes') => [
          {'name': 'Plumber.md', 'title': 'Plumber', 'tags': ['home'], 'created': '2026-10-15 10:00', 'updated': '2026-10-17 09:12',
           'preview': 'Ahmed, 0300 1234567. Comes on Tuesdays.'},
          {'name': 'Trip ideas.md', 'title': 'Trip ideas', 'tags': [], 'created': '2026-10-10 18:00', 'updated': '2026-10-12 21:40',
           'preview': 'Hunza, Skardu, Fairy Meadows. Book the jeep early.'},
        ],
      ('GET', '/api/notes/Plumber.md') => {'name': 'Plumber.md', 'path': '/home/alex/Documents/Lumen Notes/Plumber.md',
          'title': 'Plumber', 'text': 'Ahmed, **0300 1234567**.\n\nComes on Tuesdays.\n', 'tags': ['home'],
          'created': '2026-10-15 10:00', 'updated': '2026-10-17 09:12'},
      ('GET', '/api/lists') => [
          {'id': 1, 'name': 'To-do', 'position': 0, 'open': 2},
          {'id': 2, 'name': 'Shopping', 'position': 1, 'open': 3},
        ],
      ('GET', '/api/todos') => req.url.queryParameters['done'] == 'true'
          ? []
          : [
              {'id': 1, 'list_id': 1, 'list': 'To-do', 'text': 'Renew the car insurance', 'notes': '', 'priority': 3,
               'due_at': _at, 'done_at': null, 'position': 0},
              {'id': 2, 'list_id': 1, 'list': 'To-do', 'text': 'Fix the kitchen tap', 'notes': '', 'priority': 0,
               'due_at': null, 'done_at': null, 'position': 1},
            ],
      ('GET', '/api/reminders') => [
          {'id': 7, 'todo_id': null, 'text': 'Pay the rent', 'at': _at, 'repeat': 'weekly', 'next_at': _at, 'last_fired': null,
           'acknowledged': true, 'active': true, 'when': 'tomorrow at 09:00, every week'},
          {'id': 8, 'todo_id': null, 'text': 'Call the dentist', 'at': _at, 'repeat': 'none', 'next_at': _at, 'last_fired': null,
           'acknowledged': true, 'active': true, 'when': 'tomorrow at 09:00'},
        ],
      ('GET', '/api/reminders/due') => due,
      ('GET', '/api/chats') => [],
      ('POST', '/api/todos') => {'id': 5, 'list_id': 1, 'list': 'To-do', 'text': 'Buy stamps', 'notes': '', 'priority': 0,
          'due_at': _at, 'done_at': null, 'position': 2},
      _ => {'ok': true},
    };
    return http.Response.bytes(utf8.encode(jsonEncode(body)), 200, headers: {'content-type': 'application/json'});
  });
}

Future<(AppState, FakeServer)> app(WidgetTester tester) async {
  final server = FakeServer();
  final state = AppState(Api('http://laptop', client: server.client));
  await tester.runAsync(state.connect);
  return (state, server);
}

Future<void> show(WidgetTester tester, Widget child, {Size size = const Size(1440, 900)}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(debugShowCheckedModeBanner: false, theme: buildTheme(), home: Scaffold(body: child)));
  for (var i = 0; i < 4; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  setUpAll(loadFonts);

  testWidgets('notes: the list and an open note', (tester) async {
    final (state, _) = await app(tester);
    await show(tester, PlannerScreen(state: state));
    expect(find.text('Plumber'), findsOneWidget);
    expect(find.text('Trip ideas'), findsOneWidget);
    await tester.tap(find.text('Plumber'));
    for (var i = 0; i < 3; i++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(find.text('/home/alex/Documents/Lumen Notes/Plumber.md'), findsOneWidget);
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('screens/planner_notes.png'));
  });

  testWidgets('to-dos: lists, priorities, due times; adding one sends it', (tester) async {
    final (state, server) = await app(tester);
    await show(tester, PlannerScreen(state: state));
    await tester.tap(find.text('To-dos'));
    for (var i = 0; i < 3; i++) {
      await tester.pump(const Duration(milliseconds: 300));
    }
    expect(find.text('Renew the car insurance'), findsOneWidget);
    expect(find.text('Shopping'), findsOneWidget);
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('screens/planner_todos.png'));

    await tester.enterText(find.widgetWithText(TextField, 'Add to To-do…'), 'Buy stamps');
    await tester.enterText(find.widgetWithText(TextField, 'Due (e.g. Friday 5pm)'), 'Friday 5pm');
    await tester.tap(find.byTooltip('Add'));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    expect(server.calls, contains(contains('POST /api/todos {"text":"Buy stamps","list_id":1,"due":"Friday 5pm","priority":0}')));
  });

  testWidgets('reminders: upcoming and repeating', (tester) async {
    final (state, _) = await app(tester);
    await show(tester, PlannerScreen(state: state));
    await tester.tap(find.text('Reminders'));
    for (var i = 0; i < 3; i++) {
      await tester.pump(const Duration(milliseconds: 300));
    }
    expect(find.text('tomorrow at 09:00, every week'), findsOneWidget);
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('screens/planner_reminders.png'));
  });

  testWidgets('a reminder that went off is a banner above the message box: Snooze and Done', (tester) async {
    final (state, server) = await app(tester);
    server.due = [
      {'id': 7, 'todo_id': null, 'text': 'Pay the rent', 'at': _at, 'repeat': 'weekly', 'next_at': _at, 'last_fired': _at,
       'acknowledged': false, 'active': true, 'when': 'tomorrow at 09:00, every week'},
      {'id': 9, 'todo_id': null, 'text': 'Take the cake out', 'at': _at, 'repeat': 'none', 'next_at': null, 'last_fired': _at,
       'acknowledged': false, 'active': false, 'when': 'today at 16:00'},
    ];
    await tester.runAsync(state.refreshReminders);
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(debugShowCheckedModeBanner: false, theme: buildTheme(), home: DesktopShell(state: state)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Pay the rent'), findsOneWidget);
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('screens/reminder_banner.png'));

    await tester.tap(find.text('Snooze 10 min').first);
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    expect(server.calls, contains('POST /api/reminders/7/snooze {"minutes":10}'));
    await tester.tap(find.text('Done'));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    expect(server.calls, anyElement(startsWith('POST /api/reminders/9/ack')));
    expect(find.text('Take the cake out'), findsNothing);
  });

  testWidgets('chat shows what was saved, with Undo', (tester) async {
    final (state, server) = await app(tester);
    state
      ..apply(ChatEvent('user', {'text': 'remind me every Monday at 9 to pay the rent'}))
      ..apply(ChatEvent('reminder_set', {
        'reminder': {'id': 7, 'text': 'pay the rent', 'at': _at, 'repeat': 'weekly', 'next_at': _at, 'active': true,
                     'acknowledged': true, 'when': 'Monday at 09:00, every week'}
      }))
      ..apply(ChatEvent('todo_added', {
        'todo': {'id': 3, 'list_id': 2, 'list': 'Shopping', 'text': 'milk', 'notes': '', 'priority': 0, 'due_at': null,
                 'done_at': null, 'position': 0}
      }))
      ..apply(ChatEvent('note_saved', {'name': 'Plumber.md', 'title': 'Plumber', 'added_to': false, 'action_id': 'a1b2c3'}));
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(debugShowCheckedModeBanner: false, theme: buildTheme(), home: DesktopShell(state: state)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Reminder: pay the rent · Monday at 09:00, every week'), findsOneWidget);
    expect(find.text('Added “milk” to Shopping'), findsOneWidget);
    expect(find.text('Saved the note “Plumber”'), findsOneWidget);

    await tester.tap(find.text('Undo').first);
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    expect(server.calls, anyElement(startsWith('DELETE /api/reminders/7')));
    expect(find.text('Undone. Reminder: pay the rent · Monday at 09:00, every week'), findsOneWidget);
  });

  testWidgets('on the phone: one column, lists as chips', (tester) async {
    final (state, _) = await app(tester);
    await show(tester, PlannerScreen(state: state, compact: true), size: const Size(412, 860));
    await tester.tap(find.text('To-dos'));
    for (var i = 0; i < 3; i++) {
      await tester.pump(const Duration(milliseconds: 300));
    }
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('screens/mobile_todos.png'));
  });
}
