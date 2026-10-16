// The Sync tab's "Respect .gitignore files" switch.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumen_app/core/app_state.dart';
import 'package:lumen_app/features/sync/sync_screen.dart';
import 'package:lumen_app/shared/theme.dart';

import 'helpers.dart';

void main() {
  testWidgets('turning off .gitignore files saves it and re-indexes', (tester) async {
    final calls = <String>[];
    var settings = jsonDecode(fixture('settings')) as Map<String, dynamic>;
    final api = Api('http://laptop', client: MockClient((req) async {
      if (req.method != 'GET') calls.add('${req.method} ${req.url.path} ${req.body}');
      final body = switch (req.url.path) {
        '/api/status' => fixture('status'),
        '/api/settings' when req.method == 'PUT' => () {
            settings = {...settings, ...jsonDecode(req.body) as Map<String, dynamic>};
            return jsonEncode(settings);
          }(),
        '/api/settings' => jsonEncode(settings),
        '/api/index' when req.method == 'GET' => fixture('index'),
        _ => '{}',
      };
      return http.Response.bytes(utf8.encode(body), 200, headers: {'content-type': 'application/json'});
    }));
    final s = AppState(api);
    await tester.runAsync(s.connect);
    tester.view.physicalSize = const Size(1200, 1300);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: Scaffold(body: IndexScreen(state: s))));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
    await tester.pump(const Duration(milliseconds: 300));

    final toggle = find.ancestor(of: find.text('Respect .gitignore files'), matching: find.byType(Row)).first;
    final sw = find.descendant(of: toggle, matching: find.byType(Switch));
    expect(tester.widget<Switch>(sw).value, isTrue); // on unless turned off
    await tester.ensureVisible(sw);
    await tester.tap(sw);
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(calls, containsAllInOrder(['PUT /api/settings {"gitignore":false}', 'POST /api/index {}']));
    expect(tester.widget<Switch>(sw).value, isFalse);
    await tester.pump(const Duration(seconds: 5)); // snackbar and poll timers
  });
}
