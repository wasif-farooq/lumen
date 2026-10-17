// While Lumen works, the status line above the message box says what it is doing; the chat shows
// only what came of it (no step-by-step tool calls).
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumen_app/core/app_state.dart';
import 'package:lumen_app/features/shell/desktop_shell.dart';
import 'package:lumen_app/shared/theme.dart';

import 'helpers.dart';

void main() {
  setUpAll(loadFonts);

  testWidgets('the current step is a status line above the message box, not part of the chat', (tester) async {
    final state = AppState(Api('http://laptop', client: MockClient((req) async {
      final body = switch (req.url.path) {
        '/api/status' => fixture('status'),
        '/api/chats' => '[]',
        _ => '[]',
      };
      return http.Response.bytes(utf8.encode(body), 200, headers: {'content-type': 'application/json'});
    })));
    await tester.runAsync(state.connect);
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: DesktopShell(state: state)));
    await tester.pump(const Duration(milliseconds: 300));

    state
      ..apply(ChatEvent('user', {'text': 'my tax files'}))
      ..apply(ChatEvent('tool_call', {'name': 'search_files', 'args': {'query': 'tax', 'ext': 'pdf'}}));
    await tester.pump();
    expect(find.text('Searching your files · “tax” · PDF…'), findsOneWidget); // the status line
    expect(find.textContaining('search_files'), findsNothing);
    expect(find.textContaining('Searched'), findsNothing); // no step chip in the chat

    state
      ..apply(ChatEvent('answer', {'text': 'Nothing about tax yet.'}))
      ..setWorking(null);
    await tester.pump();
    expect(find.text('Nothing about tax yet.'), findsOneWidget);
    expect(find.textContaining('Searching your files'), findsNothing); // the status line is gone
    expect(state.events.map((e) => e.type), contains('tool_call')); // still in the history
  });
}
