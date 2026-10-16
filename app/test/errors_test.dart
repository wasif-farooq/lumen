// How the app shows errors: the server's message, Details with the request id, Retry for what
// didn't load, and a clear message when the laptop can't be reached.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumen_app/core/app_state.dart';
import 'package:lumen_app/features/settings/general_settings.dart';
import 'package:lumen_app/features/sync/sync_screen.dart';
import 'package:lumen_app/shared/theme.dart';

import 'helpers.dart';

http.Response json(Object body, [int status = 200]) =>
    http.Response.bytes(utf8.encode(jsonEncode(body)), status, headers: {'content-type': 'application/json'});

Map<String, dynamic> serverError(int status, String code, String message, {String hint = '', String id = 'ab12cd34'}) =>
    {'detail': message, 'error': {'code': code, 'message': message, 'hint': hint, 'id': id}};

Future<void> show(WidgetTester tester, Widget child) async {
  tester.view.physicalSize = const Size(1200, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: Scaffold(body: child)));
  await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
  await tester.pump(const Duration(milliseconds: 300));
}

void main() {
  test("the server's error answer becomes an ApiError with its message, hint and id", () {
    final e = ApiError.fromResponse(409, serverError(409, 'conflict', 'Indexing is running', hint: 'Stop it first'));
    expect([e.status, e.code, e.message, e.hint, e.id], [409, 'conflict', 'Indexing is running', 'Stop it first', 'ab12cd34']);
    final old = ApiError.fromResponse(404, {'detail': 'No such chat'});
    expect([old.message, old.code], ['No such chat', '']);
    expect(ApiError.fromResponse(502, null).message, 'HTTP 502');
  });

  test('reads are tried twice when nobody answers; changes are not repeated', () async {
    var calls = 0;
    final api = Api('http://laptop', client: MockClient((req) async {
      calls++;
      throw http.ClientException('Connection refused');
    }));
    await expectLater(api.status(), throwsA(isA<ApiError>().having((e) => e.kind, 'kind', ApiErrorKind.unreachable)));
    expect(calls, 2);
    calls = 0;
    await expectLater(api.runIndex(), throwsA(isA<ApiError>()));
    expect(calls, 1);
  });

  testWidgets('a failed action says why, and Details shows the hint and request id', (tester) async {
    final api = Api('http://laptop', client: MockClient((req) async => switch (req.url.path) {
          '/api/status' => http.Response(fixture('status'), 200),
          '/api/settings' => http.Response(fixture('settings'), 200),
          '/api/index/pause' => json(serverError(409, 'conflict', 'Indexing already finished', hint: 'Nothing to pause.'), 409),
          '/api/index' => json({'running': true, 'phase': 'scan', 'lines': ['Indexing: ~/Documents']}),
          _ => http.Response('[]', 200),
        }));
    final s = AppState(api);
    await tester.runAsync(s.connect);
    await show(tester, IndexScreen(state: s));
    await tester.tap(find.text('Pause'));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Could not pause: Indexing already finished'), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 500)); // the snackbar slides in
    await tester.tap(find.text('Details'));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('What went wrong'), findsOneWidget);
    expect(find.text('Nothing to pause.'), findsOneWidget);
    expect(find.textContaining('Request id ab12cd34'), findsOneWidget);
    await tester.tap(find.text('Close'));
    await tester.pump(const Duration(seconds: 5)); // snackbar and poll timers
  });

  testWidgets("what didn't load shows the reason and Retry loads it again", (tester) async {
    var failing = true;
    final api = Api('http://laptop', client: MockClient((req) async => switch (req.url.path) {
          '/api/status' => http.Response(fixture('status'), 200),
          '/api/settings' when failing =>
            json(serverError(500, 'internal', 'Something went wrong (id 9f8e7d6c). The details are in the log.', id: '9f8e7d6c'), 500),
          '/api/settings' => http.Response(fixture('settings'), 200),
          _ => http.Response('[]', 200),
        }));
    final s = AppState(api);
    await tester.runAsync(s.connect);
    await show(tester, GeneralSettings(state: s));
    expect(find.text("Couldn't load the settings"), findsOneWidget);
    expect(find.text('Something went wrong (id 9f8e7d6c). The details are in the log.'), findsOneWidget);
    failing = false;
    await tester.tap(find.text('Retry'));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text("Couldn't load the settings"), findsNothing);
    expect(find.text('Describe images and scans'), findsOneWidget);
  });

  testWidgets('an index run that crashed says so, with where the log is', (tester) async {
    final api = Api('http://laptop', client: MockClient((req) async => switch (req.url.path) {
          '/api/status' => http.Response(fixture('status'), 200),
          '/api/settings' => http.Response(fixture('settings'), 200),
          '/api/index' => json({
              'running': false,
              'lines': <String>[],
              'error': 'Indexing stopped unexpectedly: MemoryError. Details: /home/alex/.local/state/lumen/indexer.log',
            }),
          _ => http.Response('[]', 200),
        }));
    final s = AppState(api);
    await tester.runAsync(s.connect);
    await show(tester, IndexScreen(state: s));
    expect(find.text('Indexing stopped unexpectedly'), findsOneWidget);
    expect(find.textContaining('indexer.log'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
  });

  test('a chat that loses the laptop says so instead of failing silently', () async {
    var up = true;
    final api = Api('http://laptop', client: MockClient((req) async {
      if (!up) throw http.ClientException('Connection refused');
      return switch (req.url.path) {
        '/api/status' => http.Response(fixture('status'), 200),
        '/api/chats' when req.method == 'POST' => json({'id': 'c1', 'title': 'New chat'}),
        _ => http.Response('[]', 200),
      };
    }));
    final s = AppState(api);
    await s.connect();
    s.chatId = 'c1';
    up = false;
    await s.send('find my invoices');
    expect(s.busy, isFalse);
    expect(s.events.last.type, 'error');
    expect(s.events.last.text, startsWith('Lost connection to '));
    expect(s.events.last.text, contains("Can't reach Lumen at http://laptop."));
  });

  test('connecting to a laptop that is not there gives a message, not an exception', () async {
    final s = AppState(Api('http://laptop', client: MockClient((req) async => throw http.ClientException('refused'))));
    expect(await s.connect(), isFalse);
    expect(s.connectError, "Can't reach Lumen at http://laptop.");
  });
}
