// Mailboxes in the app, against a fake server (made-up mail of user "alex").
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumen_app/core/app_state.dart';
import 'package:lumen_app/features/mail/mail_settings.dart';
import 'package:lumen_app/features/shell/desktop_shell.dart';
import 'package:lumen_app/features/viewer/viewer_screen.dart';
import 'package:lumen_app/shared/theme.dart';

import 'helpers.dart';

const _statement = 'Hi Alex,\n\nYour berth fee for October is 120 EUR, due by the 31st.\n\nThe statement is attached.\n\nHarbour office';
final _when = DateTime(2026, 10, 16, 9, 30).millisecondsSinceEpoch / 1000;

final _accounts = [
  {'id': 'a1', 'email': 'alex@example.com', 'host': 'imap.example.com', 'port': 993, 'security': 'ssl', 'user': 'alex@example.com',
    'since_days': 365, 'added': 0, 'mails': 1284, 'state': 'ok', 'last': _when},
  {'id': 'a2', 'email': 'alex.work@example.org', 'host': 'mail.example.org', 'port': 993, 'security': 'ssl', 'user': 'alex',
    'since_days': 365, 'added': 0, 'mails': 0, 'state': 'error', 'error': "The mail server didn't accept the sign-in: LOGIN failed"},
];

class FakeMail {
  final asked = <String>[];
  final bodies = <String, Object?>{};
  late final Api api = Api('http://laptop', client: MockClient((req) async {
    asked.add('${req.method} ${req.url.path}');
    if (req.body.isNotEmpty) bodies[req.url.path] = jsonDecode(req.body);
    final (status, body) = _answer(req.method, req.url.path, req.url.queryParameters);
    return http.Response.bytes(utf8.encode(jsonEncode(body)), status, headers: {'content-type': 'application/json'});
  }));

  (int, Object) _answer(String method, String path, Map<String, String> q) => switch ((method, path)) {
        ('GET', '/api/mail/accounts') => (200, _accounts),
        ('GET', '/api/mail/guess') => (200, {'host': 'imap.gmail.com', 'port': 993, 'security': 'ssl', 'hint': 'Gmail: use an app password.'}),
        ('POST', '/api/mail/accounts') => (200, {..._accounts.first, 'id': 'a3', 'email': 'alex@gmail.com', 'state': 'waiting', 'mails': 0}),
        ('DELETE', _) => (200, {'deleted': 'alex.work@example.org'}),
        ('GET', '/api/view') when q['path']!.startsWith('mail:') =>
          (200, {'path': q['path'], 'name': 'Harbour berth statement', 'ext': 'eml', 'kind': 'mail', 'size': 4200}),
        ('GET', '/api/view') => (200, {'path': q['path'], 'name': 'statement-oct.txt', 'ext': 'txt', 'kind': 'text', 'size': 40}),
        ('GET', '/api/view/text') => (200, {'offset': 0, 'next': 40, 'done': true, 'size': 40, 'text': 'Mooring invoice 7781, sailboat Petrel'}),
        ('GET', '/api/mail/messages/12') => (200, {
            'id': 12, 'path': 'mail:12', 'account': 'a1', 'folder': 'INBOX', 'sender': 'office@harbour.example',
            'sender_name': 'Harbour office', 'recipients': 'alex@example.com', 'subject': 'Harbour berth statement',
            'date': _when, 'text': _statement,
            'attachments': [{'idx': 0, 'name': 'statement-oct.txt', 'type': 'text/plain', 'size': 40, 'has_text': true}],
          }),
        ('POST', '/api/mail/messages/12/attachments/0') =>
          (200, {'path': '/home/alex/.local/share/lumen/mail-cache/a1/12-0/statement-oct.txt', 'name': 'statement-oct.txt', 'ext': 'txt', 'kind': 'text', 'size': 40}),
        ('GET', '/api/status') => (200, jsonDecode(fixture('status')) as Object),
        _ => (200, <Object>[]),
      };
}

Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 4; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
    await tester.pump(const Duration(milliseconds: 100));
  }
}

Future<void> show(WidgetTester tester, Widget child, {Size size = const Size(1200, 800)}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(debugShowCheckedModeBanner: false, theme: buildTheme(), home: Scaffold(body: child)));
  await settle(tester);
}

void main() {
  setUpAll(loadFonts);

  testWidgets('Settings → Mail: each mailbox with how its reading is going', (tester) async {
    final f = FakeMail();
    await show(tester, MailSettings(state: AppState(f.api)));
    expect(find.text('alex@example.com'), findsOneWidget);
    expect(find.textContaining('1284 mails indexed'), findsOneWidget);
    expect(find.textContaining("didn't accept the sign-in"), findsOneWidget);
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('screens/desktop_mail_settings.png'));
  });

  testWidgets('adding a mailbox: the server is filled in, then it connects', (tester) async {
    final f = FakeMail();
    await show(tester, MailSettings(state: AppState(f.api)));
    await tester.tap(find.text('Add a mailbox'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Email address'), 'alex@gmail.com');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await settle(tester);
    expect(find.text('Gmail: use an app password.'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'Password or app password'), 'abcd efgh ijkl mnop');
    await tester.tap(find.text('Connect'));
    await settle(tester);
    expect(f.bodies['/api/mail/accounts'], containsPair('email', 'alex@gmail.com'));
    expect(f.bodies['/api/mail/accounts'], containsPair('host', 'imap.gmail.com'));
    expect(f.bodies['/api/mail/accounts'], containsPair('since_days', 365));
    expect(find.text('Add a mailbox'), findsOneWidget); // the dialog closed
  });

  testWidgets('removing a mailbox asks first', (tester) async {
    final f = FakeMail();
    await show(tester, MailSettings(state: AppState(f.api)));
    await tester.tap(find.text('Remove').last);
    await tester.pumpAndSettle();
    expect(find.textContaining('Nothing in the mailbox itself is touched'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Remove'));
    await settle(tester);
    expect(f.asked, contains('DELETE /api/mail/accounts/a2'));
  });

  testWidgets('a mail found in chat opens to be read, and its attachment in the viewer', (tester) async {
    final f = FakeMail();
    final state = AppState(f.api)
      ..apply(ChatEvent('user', {'text': 'the email about the berth fee'}))
      ..apply(ChatEvent('results', {
        'hits': [
          {'path': 'mail:12', 'name': 'Harbour berth statement', 'ext': 'eml', 'kind': 'mail', 'sender': 'Harbour office',
            'snippet': 'Your [berth] fee for October', 'size': 4200, 'mtime': _when},
        ]
      }));
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(debugShowCheckedModeBanner: false, theme: buildTheme(), home: DesktopShell(state: state)));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Email from Harbour office · Oct 16, 2026'), findsOneWidget);
    await tester.tap(find.text('Read'));
    await settle(tester);
    expect(find.text('Harbour office <office@harbour.example>'), findsOneWidget);
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('screens/viewer_mail.png'));

    await tester.tap(find.textContaining('statement-oct.txt'));
    await settle(tester);
    expect(f.asked, contains('POST /api/mail/messages/12/attachments/0'));
    expect(find.textContaining('Mooring invoice 7781'), findsOneWidget);
    await tester.tap(find.byTooltip('Back (Esc)'));
    await settle(tester);
    expect(find.text('Harbour berth statement'), findsWidgets); // back to the mail, not out of the viewer
    expect(find.textContaining('120 EUR'), findsOneWidget);
  });

  testWidgets('a mail has no "open on the laptop" or "show in folder"', (tester) async {
    final f = FakeMail();
    await show(tester, ViewerScreen(api: f.api, targets: [ViewTarget('mail:12', 'Harbour berth statement')],
        actions: ViewerActions(close: () {}, openOnLaptop: (_, _) {}, showInFolder: (_) {}, ask: (_) {})));
    await tester.tap(find.byTooltip('More'));
    await tester.pumpAndSettle();
    expect(find.text('Show in folder'), findsNothing);
    expect(find.text('Open in default app'), findsNothing);
    expect(find.text('Ask about it'), findsOneWidget);
  });
}
