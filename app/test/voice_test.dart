// Voice chat in the app, with a fake microphone, speaker and server connection.
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumen_app/core/api/voice_link.dart';
import 'package:lumen_app/core/app_state.dart';
import 'package:lumen_app/core/audio/audio_out.dart';
import 'package:lumen_app/core/audio/microphone.dart';
import 'package:lumen_app/features/shell/desktop_shell.dart';
import 'package:lumen_app/features/voice/voice_controller.dart';
import 'package:lumen_app/shared/theme.dart';

import 'helpers.dart';

class FakeMic implements Microphone {
  final audio = StreamController<Uint8List>.broadcast();
  bool started = false;
  MicrophoneError? refuse;

  @override
  Future<Stream<Uint8List>> start() async {
    if (refuse != null) throw refuse!;
    started = true;
    return audio.stream;
  }

  @override
  Future<void> stop() async => started = false;

  Future<void> dispose() => audio.close();
}

class FakeOut implements AudioOut {
  final calls = <String>[];
  int bytes = 0;
  @override
  Future<void> begin(int sampleRate) async => calls.add('begin $sampleRate');
  @override
  void add(Uint8List pcm) => bytes += pcm.length;
  @override
  Future<void> end() async => calls.add('end');
  @override
  Future<void> stopNow() async => calls.add('stop');
}

class FakeLink implements VoiceLink {
  final server = StreamController<Object>();
  final sent = <Map<String, Object?>>[];
  int audioSent = 0;
  bool closed = false;

  /// What the server says.
  void say(Map<String, Object?> event) => server.add(Map<String, dynamic>.from(event));
  void speak(int bytes) => server.add(Uint8List(bytes));

  @override
  Stream<Object> get incoming => server.stream;
  @override
  void sendAudio(Uint8List pcm) => audioSent += pcm.length;
  @override
  void send(Map<String, Object?> message) => sent.add(message);
  @override
  Future<void> close() async => closed = true;

  // Not awaited: close() waits for a listener, and a link the app never used has none.
  Future<void> dispose() async => unawaited(server.close());
}

class Rig {
  Rig() {
    state = AppState(
      Api('http://laptop', client: MockClient((req) async {
        final body = switch (req.url.path) {
          '/api/status' => fixture('status'),
          '/api/chats' => jsonEncode([
              {'id': 'v1', 'title': 'where is my invoice', 'updated': 1}
            ]),
          _ => '[]',
        };
        return http.Response.bytes(utf8.encode(body), 200, headers: {'content-type': 'application/json'});
      })),
      voiceDevices: VoiceDevices(
        microphone: () => mic,
        audioOut: () => out,
        connect: (api, chatId) async {
          connectedWith = chatId;
          if (refuseConnect != null) throw refuseConnect!;
          return link;
        },
      ),
    );
  }

  late final AppState state;
  final mic = FakeMic();
  final out = FakeOut();
  final link = FakeLink();
  String? connectedWith;
  Object? refuseConnect;

  VoiceController get voice => state.voice;
}

Future<Rig> showChat(WidgetTester tester) async {
  final rig = Rig();
  addTearDown(rig.mic.dispose);
  addTearDown(rig.link.dispose);
  await tester.runAsync(rig.state.connect);
  tester.view.physicalSize = const Size(1440, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(theme: buildTheme(), home: DesktopShell(state: rig.state)));
  await tester.pump(const Duration(milliseconds: 300));
  return rig;
}

Future<void> settle(WidgetTester tester) async {
  await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
  await tester.pump(const Duration(milliseconds: 50));
}

Future<void> turnOn(WidgetTester tester, Rig rig) async {
  await tester.tap(find.byTooltip('Talk to Lumen'));
  await settle(tester);
  rig.link.say({'type': 'ready', 'chat_id': 'v1', 'sample_rate_in': 16000, 'sample_rate_out': 22050});
  await settle(tester);
}

void main() {
  setUpAll(loadFonts);

  testWidgets('a spoken question: heard, answered in the chat, and spoken', (tester) async {
    final rig = await showChat(tester);
    await turnOn(tester, rig);
    expect(rig.connectedWith, isNull); // a new chat: the server makes it
    expect(rig.state.chatId, 'v1');
    expect(rig.mic.started, isTrue);
    expect(find.text('Listening…'), findsOneWidget);

    rig.mic.audio.add(Uint8List(640)); // hands-free: the microphone streams to the server
    await settle(tester);
    expect(rig.link.audioSent, 640);

    rig.link.say({'type': 'speech_start'});
    await settle(tester);
    expect(find.text('Hearing you…'), findsOneWidget);

    rig.link
      ..say({'type': 'transcribing'})
      ..say({'type': 'transcript', 'text': 'where is my invoice'})
      ..say({'type': 'tool_call', 'name': 'search_files', 'args': {'query': 'invoice'}})
      ..say({'type': 'speaking', 'text': 'One moment.'})
      ..speak(4410)
      ..say({'type': 'answer', 'text': 'It is invoice-1042.pdf in Documents.'})
      ..say({'type': 'speaking', 'text': 'It is invoice-1042.pdf in Documents.'})
      ..speak(4410);
    await settle(tester);
    expect(find.text('where is my invoice'), findsWidgets); // the user bubble (and the voice bar)
    expect(find.text('It is invoice-1042.pdf in Documents.'), findsOneWidget);
    expect(find.text('Speaking'), findsOneWidget);
    expect(rig.out.calls, ['begin 22050']);
    expect(rig.out.bytes, 8820);

    rig.link.say({'type': 'turn_done'});
    await settle(tester);
    expect(rig.out.calls, ['begin 22050', 'end']);
    expect(find.text('Listening…'), findsOneWidget);
    expect(rig.state.events.map((e) => e.type), containsAllInOrder(['user', 'tool_call', 'answer']));

    await tester.tap(find.byTooltip('Turn voice off'));
    await settle(tester);
    expect(rig.link.closed, isTrue);
    expect(rig.mic.started, isFalse);
    expect(find.text('Listening…'), findsNothing);
  });

  testWidgets('Stop interrupts the answer', (tester) async {
    final rig = await showChat(tester);
    await turnOn(tester, rig);
    rig.link
      ..say({'type': 'speaking', 'text': 'A long answer.'})
      ..speak(2000);
    await settle(tester);
    await tester.tap(find.text('Stop'));
    await settle(tester);
    expect(rig.link.sent, contains(equals({'type': 'interrupt'})));
    expect(rig.out.calls.last, 'stop');
  });

  testWidgets('push to talk sends audio only while the button is held', (tester) async {
    final rig = await showChat(tester);
    await turnOn(tester, rig);
    rig.voice.setMode(VoiceMode.pushToTalk);
    await settle(tester);
    expect(find.text('Hold the button and talk'), findsOneWidget);

    rig.mic.audio.add(Uint8List(640)); // not holding: nothing is sent
    await settle(tester);
    expect(rig.link.audioSent, 0);

    final gesture = await tester.startGesture(tester.getCenter(find.text('Hold to talk')));
    await settle(tester);
    rig.mic.audio.add(Uint8List(640));
    await settle(tester);
    expect(rig.link.audioSent, 640);
    await gesture.up();
    await settle(tester);
    expect(rig.link.sent, contains(equals({'type': 'stop'}))); // released: that was the question
  });

  testWidgets('with voice on, the approval buttons answer through voice', (tester) async {
    final rig = await showChat(tester);
    await turnOn(tester, rig);
    rig.link.say({'type': 'approval', 'op': 'create_folder', 'dst': '/home/alex/Documents/Invoices', 'summary': 'Create folder'});
    await settle(tester);
    await tester.tap(find.text('Approve'));
    await settle(tester);
    expect(rig.link.sent, contains(equals({'type': 'approve', 'approved': true})));
  });

  testWidgets('voice that cannot start says why, and can be tried again', (tester) async {
    final rig = await showChat(tester);
    await turnOn(tester, rig);
    rig.link.say({
      'type': 'error',
      'code': 'voice_unavailable',
      'message': "Voice chat needs its speech engine, which isn't installed.",
      'hint': 'Install it with: uv sync --extra voice',
    });
    await settle(tester);
    expect(find.textContaining('uv sync --extra voice'), findsOneWidget);
    expect(find.text('Try again'), findsOneWidget);
    expect(rig.voice.on, isFalse);
  });

  testWidgets('a microphone the app may not use is explained', (tester) async {
    final rig = await showChat(tester);
    rig.mic.refuse = MicrophoneError('Lumen may not use the microphone. Allow it in the system settings.');
    await turnOn(tester, rig);
    expect(find.text('Lumen may not use the microphone. Allow it in the system settings.'), findsOneWidget);
    expect(rig.link.closed, isTrue);
  });

  testWidgets('a laptop that is not reachable is explained', (tester) async {
    final rig = await showChat(tester);
    rig.refuseConnect = ApiError(kind: ApiErrorKind.unreachable, message: "Can't reach Lumen at http://laptop for voice.");
    await tester.tap(find.byTooltip('Talk to Lumen'));
    await settle(tester);
    expect(find.text("Can't reach Lumen at http://laptop for voice."), findsOneWidget);
  });

  testWidgets('opening another chat turns voice off', (tester) async {
    final rig = await showChat(tester);
    await turnOn(tester, rig);
    rig.state.newChat();
    await settle(tester);
    expect(rig.voice.on, isFalse);
    expect(rig.link.closed, isTrue);
  });

  testWidgets('a spoken yes closes the approval card', (tester) async {
    final rig = await showChat(tester);
    await turnOn(tester, rig);
    rig.link
      ..say({'type': 'approval', 'op': 'create_folder', 'dst': '/home/alex/Documents/Invoices', 'summary': 'Create folder'})
      ..say({'type': 'turn_done'});
    await settle(tester);
    expect(rig.state.pendingApproval, isNotNull);
    rig.link
      ..say({'type': 'transcribing'})
      ..say({'type': 'transcript', 'text': 'yes'})
      ..say({'type': 'approval_answer', 'approved': true});
    await settle(tester);
    expect(rig.state.pendingApproval, isNull);
    expect(find.text('Approve'), findsNothing);
  });

  testWidgets('a button answer is not recorded twice when the server confirms it', (tester) async {
    final rig = await showChat(tester);
    await turnOn(tester, rig);
    rig.link
      ..say({'type': 'approval', 'op': 'create_folder', 'dst': '/home/alex/Documents/Invoices', 'summary': 'Create folder'})
      ..say({'type': 'turn_done'});
    await settle(tester);
    await tester.tap(find.text('Approve'));
    await settle(tester);
    rig.link.say({'type': 'approval_answer', 'approved': true});
    await settle(tester);
    expect(rig.state.events.where((e) => e.type == 'approval_answer'), hasLength(1));
  });

  testWidgets('typing waits while a spoken turn runs', (tester) async {
    final rig = await showChat(tester);
    await turnOn(tester, rig);
    rig.link.say({'type': 'transcribing'});
    await settle(tester);
    expect(rig.state.voiceTurn, isTrue);
    final events = rig.state.events.length;
    await rig.state.send('and my passport?');
    expect(rig.state.events, hasLength(events)); // not sent
    rig.link.say({'type': 'turn_done'});
    await settle(tester);
    expect(rig.state.voiceTurn, isFalse);
  });

  testWidgets('turning voice off while it connects leaves nothing open', (tester) async {
    final rig = Rig();
    addTearDown(rig.mic.dispose);
    addTearDown(rig.link.dispose);
    final connecting = Completer<VoiceLink>();
    final voice = VoiceController(rig.state,
        devices: VoiceDevices(microphone: () => rig.mic, audioOut: () => rig.out, connect: (_, _) => connecting.future));
    final starting = voice.start();
    await voice.stop();
    connecting.complete(rig.link);
    await tester.pump();
    await starting;
    expect(voice.on, isFalse);
    expect(rig.link.closed, isTrue);
    expect(rig.state.onApprove, isNull);
  });

  testWidgets('after Stop, the rest of that answer is not played', (tester) async {
    final rig = await showChat(tester);
    await turnOn(tester, rig);
    rig.link
      ..say({'type': 'speaking', 'text': 'A long answer.'})
      ..speak(2000);
    await settle(tester);
    await tester.tap(find.text('Stop'));
    await settle(tester);
    rig.link.speak(3000); // already on its way when the server stopped
    await settle(tester);
    expect(rig.out.bytes, 2000);
    rig.link
      ..say({'type': 'speaking', 'text': 'Next answer.'})
      ..speak(1000);
    await settle(tester);
    expect(rig.out.bytes, 3000);
  });

  testWidgets('a laptop without the speech engine offers no microphone', (tester) async {
    final rig = await showChat(tester);
    rig.state.status = {...?rig.state.status, 'voice': false};
    rig.state.select(null); // rebuild
    await tester.pump();
    expect(find.byTooltip('Talk to Lumen'), findsNothing);
  });
}
