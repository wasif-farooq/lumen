// Renders the real screens against recorded API responses (test/fixtures) and
// saves screenshots: flutter test --update-goldens
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumen_app/core/app_state.dart';
import 'package:lumen_app/features/shell/desktop_shell.dart';
import 'package:lumen_app/features/sync/sync_screen.dart';
import 'package:lumen_app/features/shell/mobile_chat.dart';
import 'package:lumen_app/features/models/models_screen.dart';
import 'package:lumen_app/features/settings/settings_screen.dart';
import 'package:lumen_app/shared/theme.dart';
import 'package:lumen_app/shared/widgets/zoom.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'helpers.dart';

Api fakeApi() => Api('http://laptop', client: MockClient((req) async {
      final p = req.url.path;
      String body = switch (p) {
        '/api/status' => fixture('status'),
        '/api/chats' => fixture('chats'),
        '/api/settings' => fixture('settings'),
        '/api/index' => fixture('index'),
        '/api/devices' => '[]',
        '/api/providers' => fixture('providers'),
        '/api/file' => req.url.queryParameters['path']!.endsWith('.avi') ? fixture('file_video') : fixture('file_tax'),
        _ when p.endsWith('/events') => '[]',
        _ => '{}',
      };
      return http.Response.bytes(utf8.encode(body), 200, headers: {'content-type': 'application/json'});
    }));

Future<AppState> stateWith(String eventsFixture) async {
  final s = AppState(fakeApi());
  await s.connect();
  final chats = s.chats;
  s.chatId = chats.isNotEmpty ? chats.first.id : 'c';
  s.events = [for (final e in jsonDecode(fixture(eventsFixture)) as List) ChatEvent.fromJson(Map<String, dynamic>.from(e as Map))];
  final results = s.events.where((e) => e.type == 'results').toList();
  s.selected = results.isEmpty ? null : results.last.hits.first;
  return s;
}

Future<void> shot(WidgetTester tester, Widget child, Size size, String name) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(debugShowCheckedModeBanner: false, theme: buildTheme(), home: child));
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(milliseconds: 300));
  }
  await expectLater(find.byType(MaterialApp), matchesGoldenFile('screens/$name.png'));
}

void main() {
  setUpAll(loadFonts);

  testWidgets('desktop chat with document results', (tester) async {
    final s = await tester.runAsync(() => stateWith('events_tax'));
    await shot(tester, DesktopShell(state: s!), const Size(1440, 900), 'desktop_chat');
    expect(find.text('tax-return-2025.pdf'), findsWidgets);
  });

  testWidgets('desktop chat with a video found by speech', (tester) async {
    final s = await tester.runAsync(() => stateWith('events_video'));
    await shot(tester, DesktopShell(state: s!), const Size(1440, 900), 'desktop_video');
    expect(find.textContaining('Play at 10:05'), findsWidgets);
  });

  testWidgets('index and power', (tester) async {
    final s = await tester.runAsync(() async {
      final s = AppState(fakeApi());
      await s.connect();
      return s;
    });
    await shot(tester, Scaffold(body: IndexScreen(state: s!)), const Size(1200, 1000), 'desktop_index');
    expect(find.text('Sync'), findsOneWidget);
  });

  testWidgets('models: roles, providers and switching chat to a cloud model', (tester) async {
    final calls = <String>[];
    var providers = jsonDecode(fixture('providers')) as Map<String, dynamic>;
    providers['pulls'] = [];
    final api = Api('http://laptop', client: MockClient((req) async {
      final p = req.url.path;
      if (req.method != 'GET') calls.add('${req.method} $p ${req.body}');
      final body = switch (p) {
        '/api/status' => fixture('status'),
        '/api/providers' => jsonEncode(providers),
        '/api/providers/openrouter/models' => jsonEncode([
            {'id': 'anthropic/claude-haiku', 'size': null, 'vision': null},
            {'id': 'openai/gpt-mini', 'size': null, 'vision': null},
          ]),
        '/api/roles' => '{}',
        '/api/models/check' => jsonEncode((jsonDecode(req.body) as Map)['model'] == 'openai/gpt-mini'
            ? {'ok': true, 'seconds': 2.1, 'checks': [
                {'name': 'Answers', 'ok': true, 'detail': 'The model replied.'},
                {'name': 'Calls tools', 'ok': true, 'detail': 'Asked to search: called search_files'},
              ]}
            : {'ok': false, 'seconds': 3.4, 'checks': [
                {'name': 'Answers', 'ok': true, 'detail': 'The model replied.'},
                {'name': 'Calls tools', 'ok': false, 'detail': 'It answered in text instead of calling the search tool.'},
              ]}),
        _ => '{}',
      };
      return http.Response.bytes(utf8.encode(body), 200, headers: {'content-type': 'application/json'});
    }));
    final s = AppState(api);
    await tester.runAsync(s.connect);
    tester.view.physicalSize = const Size(1200, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: Scaffold(body: ModelsScreen(state: s))));
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('qwen2.5vl:3b'), findsOneWidget);
    expect(find.text('OpenRouter'), findsOneWidget);

    await tester.tap(find.text('Change').first); // chat agent
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('OpenRouter').last);
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await tester.pumpAndSettle();
    await tester.tap(find.text('anthropic/claude-haiku'));
    await tester.pump();
    await tester.tap(find.text('Use this model'));
    await tester.pumpAndSettle();
    expect(find.text('Send to the cloud'), findsOneWidget); // cloud warning comes before anything is sent
    expect(calls.where((c) => c.contains('/api/models/check')), isEmpty);
    await tester.tap(find.text('Send to the cloud'));
    await tester.pump(const Duration(milliseconds: 300)); // check dialog opens and starts the check
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await tester.pump(const Duration(milliseconds: 300));
    // The check fails: no tool calling. Pick another model instead.
    expect(find.text('anthropic/claude-haiku may not work for chat'), findsOneWidget);
    expect(find.text('It answered in text instead of calling the search tool.'), findsOneWidget);
    await tester.tap(find.text('Pick another'));
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await tester.pumpAndSettle();
    await tester.tap(find.text('openai/gpt-mini'));
    await tester.pump();
    await tester.tap(find.text('Use this model'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Send to the cloud'));
    await tester.pump(const Duration(milliseconds: 300)); // check dialog opens and starts the check
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('openai/gpt-mini works for chat'), findsOneWidget);
    await tester.tap(find.text('Use this model'));
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(calls, contains('PUT /api/roles {"role":"agent","provider":"openrouter","model":"openai/gpt-mini"}'));
    expect(calls.where((c) => c.contains('anthropic/claude-haiku') && c.startsWith('PUT')), isEmpty);
    await tester.pump(const Duration(seconds: 5)); // let snackbar timers settle
  });

  testWidgets('models screen', (tester) async {
    final s = await tester.runAsync(() async {
      final s = AppState(fakeApi());
      await s.connect();
      return s;
    });
    await shot(tester, Scaffold(body: ModelsScreen(state: s!)), const Size(1200, 900), 'desktop_models');
    expect(find.text('What each job uses'), findsOneWidget);
  });

  testWidgets('settings', (tester) async {
    final s = await tester.runAsync(() async {
      final s = AppState(fakeApi());
      await s.connect();
      return s;
    });
    await shot(tester, Scaffold(body: SettingsScreen(state: s!)), const Size(1200, 1000), 'desktop_settings');
    expect(find.text('Settings'), findsOneWidget);
    expect(find.text('Describe images and scans'), findsOneWidget);
    expect(find.text('Pair a phone'), findsOneWidget);
    await tester.tap(find.text('Models'));
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await tester.pumpAndSettle();
    expect(find.text('What each job uses'), findsOneWidget);
    await tester.tap(find.text('Sync'));
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('Re-index now'), findsOneWidget);
    expect(find.text('Duplicates'), findsNothing);
    expect(find.text('Tracing'), findsNothing);
    await shot(tester, Scaffold(body: SettingsScreen(state: s, tab: 2)), const Size(1200, 1000), 'desktop_settings_sync');
  });

  testWidgets('settings tabs stay put when status refreshes mid-switch, and keep their state', (tester) async {
    var providerCalls = 0;
    final api = Api('http://laptop', client: MockClient((req) async {
      final p = req.url.path;
      if (p == '/api/providers') providerCalls++;
      final body = switch (p) {
        '/api/status' => fixture('status'),
        '/api/chats' => fixture('chats'),
        '/api/settings' => fixture('settings'),
        '/api/index' => fixture('index'),
        '/api/devices' => '[]',
        // no download running, so the tab isn't polling: every call here is a (re)load
        '/api/providers' => jsonEncode({...jsonDecode(fixture('providers')) as Map, 'pulls': []}),
        _ => '[]',
      };
      return http.Response.bytes(utf8.encode(body), 200, headers: {'content-type': 'application/json'});
    }));
    final s = AppState(api);
    await tester.runAsync(s.connect);
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: DesktopShell(state: s)));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text('Settings'));
    await tester.pump(const Duration(milliseconds: 300));

    Future<void> settle() async {
      for (var i = 0; i < 6; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
    }

    // Switch tab, and have the app refresh its status while the tab animation is running
    await tester.tap(find.text('Models'));
    await tester.pump(const Duration(milliseconds: 50));
    await tester.runAsync(s.refreshStatus);
    await tester.pump(const Duration(milliseconds: 50));
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await settle();
    int shown() => tester.widget<TabBar>(find.byType(TabBar)).controller!.index;
    expect(shown(), 1); // still on Models, not pulled back to General
    expect(find.text('What each job uses'), findsOneWidget);

    // A tab keeps its state: going back to Models doesn't load it again
    await tester.tap(find.text('General'));
    await settle();
    await tester.tap(find.text('Models'));
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await settle();
    expect(shown(), 1);
    expect(find.text('What each job uses'), findsOneWidget);
    expect(providerCalls, 1);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('sidebar sync tile opens the Sync tab of Settings', (tester) async {
    final s = await tester.runAsync(() async {
      final s = AppState(fakeApi());
      await s.connect();
      return s;
    });
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: DesktopShell(state: s!)));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.textContaining('files ·'));
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('Re-index now'), findsOneWidget);
    await tester.tap(find.text('General'));
    for (var i = 0; i < 6; i++) {
      await tester.pump(const Duration(milliseconds: 200));
    }
    expect(find.text('Describe images and scans'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3)); // poll timers
  });

  testWidgets('mobile chat', (tester) async {
    final s = await tester.runAsync(() => stateWith('events_tax'));
    await shot(tester, MobileChat(state: s!, onUnpair: () {}), const Size(390, 844), 'mobile_chat');
  });

  testWidgets('zoom: Ctrl + / Ctrl - / Ctrl 0 scale the whole UI', (tester) async {
    SharedPreferences.setMockInitialValues({});
    tester.view.physicalSize = const Size(1000, 700);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      builder: (c, child) => Zoom(child: child!),
      home: const Scaffold(body: Align(alignment: Alignment.topLeft, child: SizedBox(key: Key('box'), width: 100, height: 50))),
    ));
    Future<void> keys(LogicalKeyboardKey k) async {
      await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
      await tester.sendKeyEvent(k);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
      await tester.pump();
    }

    double width() => tester.getRect(find.byKey(const Key('box'))).width;
    expect(width(), 100);
    await keys(LogicalKeyboardKey.equal);
    await keys(LogicalKeyboardKey.equal);
    expect(width(), closeTo(120, 0.5));
    await keys(LogicalKeyboardKey.minus);
    expect(width(), closeTo(110, 0.5));
    await keys(LogicalKeyboardKey.digit0);
    expect(width(), 100);
    await tester.pump(const Duration(seconds: 2)); // let the "%"-badge timer finish
  });

  testWidgets('copy button copies the answer as plain text', (tester) async {
    String? clip;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') clip = (call.arguments as Map)['text'];
      return null;
    });
    final s = await tester.runAsync(() => stateWith('events_tax'));
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: DesktopShell(state: s!)));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.ensureVisible(find.byTooltip('Copy').last);
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.byTooltip('Copy').last);
    await tester.pump();
    final answer = s.events.lastWhere((e) => e.type == 'answer').text;
    expect(clip, answer.replaceAll('**', '').replaceAll('`', ''));
    await tester.pump(const Duration(seconds: 2));
  });

  testWidgets('Pause and Stop control a running index', (tester) async {
    var running = true, paused = false, stopCalls = 0;
    final api = Api('http://laptop', client: MockClient((req) async {
      final body = switch (req.url.path) {
        '/api/status' => fixture('status'),
        '/api/settings' => fixture('settings'),
        '/api/devices' => '[]',
        '/api/index/stop' => () {
            stopCalls++;
            running = false;
            return '{"stopped": true, "running": false}';
          }(),
        '/api/index/pause' => () {
            paused = true;
            return '{"pausing": true, "running": true}';
          }(),
        '/api/index/resume' => () {
            paused = false;
            return '{"running": true}';
          }(),
        '/api/index' => jsonEncode({
            'running': running,
            'paused': paused,
            'pausing': false,
            'phase': 'captions',
            'done': 37,
            'total': 120,
            'eta': 410,
            'path': '/home/alex/Pictures/beach.jpg',
            'ext': 'jpg',
            'kind': 'image',
            'note': 'A wide sandy beach at sunset with two people walking near the water.',
            'recent': [
              {'path': '/home/alex/Pictures/beach.jpg', 'note': 'A wide sandy beach…', 'kind': 'image'},
              {'path': '/home/alex/Pictures/receipt.png', 'note': 'A printed shop receipt listing groceries and a total of 42.10.', 'kind': 'image'},
              {'path': '/home/alex/Documents/scan_003.pdf', 'note': 'failed: model timed out', 'kind': 'pdf'},
            ],
            'lines': ['Indexing: ~/Pictures', '  [37/120] ~/Pictures/beach.jpg'],
          }),
        _ => '[]',
      };
      return http.Response.bytes(utf8.encode(body), 200, headers: {'content-type': 'application/json'});
    }));
    final s = AppState(api);
    await tester.runAsync(s.connect);
    await shot(tester, Scaffold(body: IndexScreen(state: s)), const Size(1200, 1300), 'desktop_index_running');
    expect(find.text('Describing images & scans'), findsOneWidget);
    expect(find.text('Step 2 of 5 · 37 of 120 · about 7 min left'), findsOneWidget);
    await tester.tap(find.text('Pause'));
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 200)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(paused, isTrue);
    expect(find.text('Resume'), findsOneWidget);
    expect(find.text('Paused'), findsWidgets);
    await shot(tester, Scaffold(body: IndexScreen(state: s)), const Size(1200, 1300), 'desktop_index_paused');
    await tester.tap(find.text('Resume'));
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 200)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(paused, isFalse);
    expect(find.text('Stop'), findsOneWidget);
    await tester.tap(find.text('Stop'));
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 200)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(stopCalls, 1);
    expect(find.text('Stop'), findsNothing);
    expect(find.text('Re-index now'), findsOneWidget);
    await tester.pump(const Duration(seconds: 5)); // let snackbar / poll timers settle
  });

  testWidgets('folder menu pauses syncing; excluded paths can be included again', (tester) async {
    final calls = <String>[];
    final api = Api('http://laptop', client: MockClient((req) async {
      final p = req.url.path;
      if (req.method == 'POST') calls.add('$p ${req.body}');
      final body = switch (p) {
        '/api/status' => fixture('status'),
        '/api/settings' => fixture('settings'),
        '/api/index' => fixture('index'),
        '/api/devices' => '[]',
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
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await tester.pump(const Duration(milliseconds: 300));

    await tester.tap(find.byTooltip('Actions for ~/Documents'));
    await tester.pumpAndSettle();
    expect(find.text('Clear indexed data…'), findsOneWidget);
    await tester.tap(find.text('Pause syncing'));
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(calls, contains('/api/folders/pause {"path":"/home/alex/Documents"}'));

    await tester.tap(find.byTooltip('Actions for ~/Desktop'));
    await tester.pumpAndSettle();
    expect(find.text('Resume syncing'), findsOneWidget);
    await tester.tapAt(const Offset(5, 5));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('Include again'));
    await tester.tap(find.text('Include again'));
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 100)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(calls, contains('/api/index/include {"path":"/home/alex/Documents/private","reindex":true}'));
    await tester.pump(const Duration(seconds: 5)); // let snackbar / poll timers settle
  });

  testWidgets('desktop chat with image search and a dropped photo', (tester) async {
    final s = await tester.runAsync(() => stateWith('events_images'));
    await shot(tester, DesktopShell(state: s!), const Size(1440, 1800), 'desktop_images');
    expect(find.text('Images like this photo'), findsOneWidget);
    expect(find.byTooltip('Find similar images'), findsWidgets);
  });

  testWidgets('approve a move, then undo it', (tester) async {
    final calls = <String>[];
    const home = '/home/alex';
    final api = Api('http://laptop', client: MockClient((req) async {
      calls.add(req.url.path);
      String sse(List<Map<String, dynamic>> evs) => evs.map((e) => 'data: ${jsonEncode(e)}\n\n').join();
      final body = switch (req.url.path) {
        '/api/status' => fixture('status'),
        '/api/chats' => fixture('chats'),
        '/api/chats/c1/approve' => sse([
            {'type': 'started'},
            {'type': 'action_done', 'id': 'a1', 'op': 'move', 'dry_run': false, 'message': 'Done: Move file $home/Downloads/invoice-1042.pdf → $home/Documents/Invoices/invoice-1042.pdf'},
            {'type': 'answer', 'text': 'Moved invoice-1042.pdf into Documents/Invoices.'},
            {'type': 'done'},
          ]),
        '/api/actions/a1/undo' => '{"ok": true, "message": "Moved back to $home/Downloads/invoice-1042.pdf"}',
        _ => '[]',
      };
      return http.Response.bytes(utf8.encode(body), 200);
    }));
    final s = AppState(api);
    await tester.runAsync(s.connect);
    s.chatId = 'c1';
    s.events = [
      ChatEvent('user', {'text': 'move the invoice from Downloads into a new Invoices folder in Documents'}),
      ChatEvent('tool_call', {'name': 'create_folder', 'args': {'path': '$home/Documents/Invoices'}}),
      ChatEvent('approval', {'op': 'create_folder', 'dst': '$home/Documents/Invoices', 'summary': 'Create folder $home/Documents/Invoices'}),
      ChatEvent('approval_answer', {'approved': true}),
      ChatEvent('action_done', {'id': 'a0', 'op': 'create_folder', 'dry_run': false, 'message': 'Done: Create folder $home/Documents/Invoices'}),
      ChatEvent('tool_call', {'name': 'move_file', 'args': {'source': '1', 'destination': '$home/Documents/Invoices'}}),
      ChatEvent('approval', {'op': 'move', 'src': '$home/Downloads/invoice-1042.pdf', 'dst': '$home/Documents/Invoices/invoice-1042.pdf', 'size': 48213, 'summary': 'Move file $home/Downloads/invoice-1042.pdf → $home/Documents/Invoices/invoice-1042.pdf'}),
    ];
    await shot(tester, DesktopShell(state: s), const Size(1440, 900), 'desktop_approval');
    expect(s.pendingApproval, isNotNull);
    expect(find.text('Approve'), findsOneWidget);

    await tester.tap(find.text('Approve'));
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 200)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(calls, contains('/api/chats/c1/approve'));
    expect(s.pendingApproval, isNull);
    expect(find.text('Approve'), findsNothing);
    expect(find.text('Undo'), findsNWidgets(2)); // the folder and the move can both be undone

    await tester.tap(find.text('Undo').last);
    await tester.runAsync(() => Future.delayed(const Duration(milliseconds: 200)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(calls, contains('/api/actions/a1/undo'));
    expect(find.textContaining('Undone. Moved back'), findsOneWidget);
    expect(find.text('Undo'), findsOneWidget);
  });

  testWidgets('desktop empty state', (tester) async {
    final s = await tester.runAsync(() async {
      final s = AppState(fakeApi());
      await s.connect();
      return s;
    });
    await shot(tester, DesktopShell(state: s!), const Size(1440, 900), 'desktop_welcome');
    expect(find.text('What are you looking for?'), findsOneWidget);
  });
}
