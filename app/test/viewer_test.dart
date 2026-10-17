// Reading files in the app, against a fake server (made-up files of user "alex").
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumen_app/core/app_state.dart';
import 'package:lumen_app/features/shell/desktop_shell.dart';
import 'package:lumen_app/features/viewer/viewer_screen.dart';
import 'package:lumen_app/shared/theme.dart';

import 'helpers.dart';

const docs = '/home/alex/Documents';

final _code = List.generate(60, (i) => i == 41 ? 'def total(rows):  # the invoice total' : 'line_$i = $i').join('\n');

const _markdown = '''# Trip to Hunza

Leave **early** on Friday; the road to *Karimabad* is slow.

- Pack warm clothes
- Book the jeep
  - ask for a driver who knows the pass

> The best time is late September.

```
budget = 45000  # rupees
```
''';

Object _answer(String path, Map<String, String> q) {
  final file = q['path'] ?? '';
  return switch (path) {
    '/api/view' => switch (file.split('.').last) {
        'pdf' => {'path': file, 'name': file.split('/').last, 'ext': 'pdf', 'kind': 'pdf', 'size': 5000, 'pages': 3,
            'shapes': [1.414, 1.414, 1.414]},
        'py' => {'path': file, 'name': 'report.py', 'ext': 'py', 'kind': 'code', 'size': _code.length, 'language': 'py'},
        'md' => {'path': file, 'name': 'trip.md', 'ext': 'md', 'kind': 'markdown', 'size': _markdown.length},
        'xlsx' => {'path': file, 'name': 'budget.xlsx', 'ext': 'xlsx', 'kind': 'table', 'size': 9000},
        _ => {'path': file, 'name': file.split('/').last, 'ext': 'bin', 'kind': 'other', 'size': 10},
      },
    '/api/view/find' => [
        {'page': 1, 'rects': [[0.1, 0.2, 0.4, 0.23]]},
      ],
    '/api/view/text' => {
        'offset': 0, 'next': (file.endsWith('.md') ? _markdown : _code).length, 'done': true,
        'size': (file.endsWith('.md') ? _markdown : _code).length, 'text': file.endsWith('.md') ? _markdown : _code,
      },
    '/api/view/blocks' => {
        'cut': false,
        'blocks': [
          {'type': 'break', 'label': 'Budget'},
          {'type': 'table', 'rows': [['Item', 'Cost'], ['Travel to Lisbon', '1200'], ['Hotel', '640'], ['Food', '300']]},
          {'type': 'break', 'label': 'Notes'},
          {'type': 'paragraph', 'text': 'Remember the parking receipts.'},
        ],
      },
    '/api/status' => jsonDecode(fixture('status')),
    _ => <Object>[],
  };
}

Future<(Api, List<String>)> fakeApi() async {
  final asked = <String>[];
  final client = MockClient((req) async {
    asked.add('${req.url.path}?${req.url.query}');
    return http.Response.bytes(utf8.encode(jsonEncode(_answer(req.url.path, req.url.queryParameters))), 200,
        headers: {'content-type': 'application/json'});
  });
  return (Api('http://laptop', client: client), asked);
}

Future<void> show(WidgetTester tester, Widget child, {Size size = const Size(1200, 800)}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(debugShowCheckedModeBanner: false, theme: buildTheme(), home: Scaffold(body: child)));
  for (var i = 0; i < 4; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
    await tester.pump(const Duration(milliseconds: 100));
  }
}

ViewerActions actions({void Function()? close, void Function(String, double)? open}) => ViewerActions(
      close: close ?? () {},
      openOnLaptop: open ?? (_, _) {},
      showInFolder: (_) {},
      ask: (_) {},
    );

void main() {
  setUpAll(loadFonts);

  testWidgets('code: line numbers, the search words marked, opens at the first one', (tester) async {
    final (api, _) = await fakeApi();
    await show(tester, ViewerScreen(api: api, targets: [ViewTarget('$docs/report.py', 'report.py', terms: ['invoice'])], actions: actions()));
    expect(find.text('42'), findsOneWidget); // the line number of the match, scrolled into view
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('screens/viewer_code.png'));
  });

  testWidgets('Markdown is formatted', (tester) async {
    final (api, _) = await fakeApi();
    await show(tester, ViewerScreen(api: api, targets: [ViewTarget('$docs/trip.md', 'trip.md', terms: ['jeep'])], actions: actions()));
    expect(find.text('Trip to Hunza'), findsOneWidget);
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('screens/viewer_markdown.png'));
  });

  testWidgets('a spreadsheet as real tables, one per sheet', (tester) async {
    final (api, _) = await fakeApi();
    await show(tester, ViewerScreen(api: api, targets: [ViewTarget('$docs/budget.xlsx', 'budget.xlsx', terms: ['Lisbon'])], actions: actions()));
    expect(find.text('Budget'), findsOneWidget);
    expect(find.text('Notes'), findsOneWidget);
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('screens/viewer_table.png'));
  });

  testWidgets('a PDF opens at the page that matched', (tester) async {
    final (api, asked) = await fakeApi();
    await show(tester, ViewerScreen(api: api, targets: [ViewTarget('$docs/tax-return.pdf', 'tax-return.pdf', terms: ['Taxpayers'])], actions: actions()));
    await tester.pump(const Duration(milliseconds: 200));
    expect(asked, contains(contains('/api/view/find?path=%2Fhome%2Falex%2FDocuments%2Ftax-return.pdf&q=Taxpayers')));
    expect(find.text('Page 2 of 3'), findsOneWidget); // jumped to the match
    expect(find.text('1/1 pages'), findsOneWidget);
  });

  testWidgets('previous / next go through the results; Esc goes back', (tester) async {
    final (api, _) = await fakeApi();
    var closed = false;
    await show(
      tester,
      ViewerScreen(
        api: api,
        targets: [ViewTarget('$docs/trip.md', 'trip.md'), ViewTarget('$docs/report.py', 'report.py')],
        actions: actions(close: () => closed = true),
      ),
    );
    expect(find.text('1/2'), findsOneWidget);
    await tester.tap(find.byTooltip('Next result'));
    for (var i = 0; i < 3; i++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(find.text('report.py'), findsOneWidget);
    expect(find.text('2/2'), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    expect(closed, isTrue);
  });

  testWidgets("a file the app can't show offers to open it on the laptop", (tester) async {
    final (api, _) = await fakeApi();
    String? opened;
    await show(tester, ViewerScreen(api: api, targets: [ViewTarget('$docs/setup.bin', 'setup.bin')], actions: actions(open: (p, _) => opened = p)));
    await tester.tap(find.text('Open on the laptop'));
    expect(opened, '$docs/setup.bin');
  });

  testWidgets('View on a search result reads it in place of the chat', (tester) async {
    final (api, _) = await fakeApi();
    final state = AppState(api)
      ..apply(ChatEvent('user', {'text': 'my trip notes'}))
      ..apply(ChatEvent('results', {
        'hits': [
          {'path': '$docs/trip.md', 'name': 'trip.md', 'ext': 'md', 'kind': 'doc', 'snippet': 'Book the [jeep]', 'size': 300, 'mtime': 1.7e9},
        ]
      }));
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(debugShowCheckedModeBanner: false, theme: buildTheme(), home: DesktopShell(state: state)));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text('View').first); // the result card (the preview panel has one too)
    for (var i = 0; i < 4; i++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(find.text('Trip to Hunza'), findsOneWidget);
    await tester.tap(find.byTooltip('Back (Esc)'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('my trip notes'), findsWidgets); // the chat again
  });

  testWidgets('on the phone: full width, find in the menu', (tester) async {
    final (api, _) = await fakeApi();
    await show(
      tester,
      ViewerScreen(api: api, targets: [ViewTarget('$docs/budget.xlsx', 'budget.xlsx')], compact: true, actions: actions()),
      size: const Size(412, 860),
    );
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('screens/mobile_viewer.png'));
  });
}
