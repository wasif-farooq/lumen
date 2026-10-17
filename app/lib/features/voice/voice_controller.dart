import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/api/voice_link.dart';
import '../../core/app_state.dart';
import '../../core/audio/audio_out.dart';
import '../../core/audio/microphone.dart';
import '../../core/errors/errors.dart';
import '../../core/logging/log.dart';
import '../chat/chat_state.dart';

const _log = Log('voice');

/// Hands-free: the server hears where each question ends. Push-to-talk: audio is sent only
/// while the talk button is held.
enum VoiceMode { handsFree, pushToTalk }

enum VoiceStatus { off, connecting, listening, hearing, thinking, speaking }

/// The microphone, speaker and connection voice uses; tests pass fakes.
class VoiceDevices {
  const VoiceDevices({required this.microphone, required this.audioOut, required this.connect});
  final Microphone Function() microphone;
  final AudioOut Function() audioOut;
  final Future<VoiceLink> Function(Api api, String? chatId) connect;

  static VoiceDevices real() =>
      VoiceDevices(microphone: RecordMicrophone.new, audioOut: SoloudOut.new, connect: WebSocketVoiceLink.connect);
}

/// Talking to Lumen: microphone audio to the server, its events into the open chat (as if typed),
/// and its spoken answer to the speaker.
class VoiceController extends ChangeNotifier {
  VoiceController(this.app, {VoiceDevices? devices}) : devices = devices ?? VoiceDevices.real();

  final ChatState app;
  final VoiceDevices devices;

  VoiceStatus status = VoiceStatus.off;
  VoiceMode mode = VoiceMode.handsFree;
  String? error; // why voice stopped, for the voice bar
  String? heard; // the last thing the server heard
  bool talking = false; // push-to-talk button held

  VoiceLink? _link;
  Microphone? _mic;
  AudioOut? _out;
  StreamSubscription<Object>? _linkSub;
  StreamSubscription<Uint8List>? _micSub;
  Future<void>? _outReady; // the speaker's stream for this turn (audio waits on it, in order)
  int _outRate = 22050;
  bool _muted = false; // after an interrupt: drop the rest of that answer's audio
  String? _chatId;
  int _session = 0; // bumped by stop(), so a connect or microphone still starting gives up
  bool _disposed = false;

  bool get on => status != VoiceStatus.off;

  // ---------- on and off ----------

  Future<void> start() async {
    if (on) return;
    final session = _session;
    error = heard = null;
    _set(VoiceStatus.connecting);
    try {
      final link = await devices.connect(app.api, app.chatId);
      if (session != _session) {
        unawaited(link.close()); // turned off while connecting
        return;
      }
      _link = link;
      _linkSub = link.incoming.listen(_onMessage, onDone: _onClosed, onError: (Object e) => _fail('Voice connection lost: $e'));
      app.addListener(_onChat);
      app.onApprove = (approved) {
        _turnStarted();
        link.send({'type': 'approve', 'approved': approved});
      };
    } on Object catch (e, st) {
      logUnexpected('voice connect', e, st);
      if (session == _session) await _fail(userMessage(e));
    }
  }

  Future<void> stop() async {
    _session++;
    app.removeListener(_onChat);
    app.onApprove = null;
    unawaited(_micSub?.cancel());
    unawaited(_linkSub?.cancel());
    final mic = _mic, out = _out, link = _link;
    _mic = null;
    _out = null;
    _link = null;
    _micSub = null;
    _linkSub = null;
    _outReady = null;
    talking = false;
    if (!_disposed) {
      app.voiceTurn = false;
      app.setWorking(null);
    }
    _set(VoiceStatus.off);
    // each one on its own, so one failing doesn't leave the others open
    for (final close in [mic?.stop, out?.stopNow, link?.close]) {
      try {
        await close?.call();
      } on Object catch (e, st) {
        logUnexpected('voice stop', e, st);
      }
    }
  }

  // ---------- talking ----------

  void setMode(VoiceMode m) {
    releaseTalk(); // switching while the button is held ends that question
    mode = m;
    notifyListeners();
  }

  /// Push-to-talk pressed: start sending audio (and stop any answer still playing).
  void pressTalk() {
    if (status == VoiceStatus.speaking) interrupt();
    talking = true;
    notifyListeners();
  }

  /// Push-to-talk released: that was the whole question.
  void releaseTalk() {
    if (!talking) return;
    talking = false;
    _link?.send({'type': 'stop'});
    notifyListeners();
  }

  /// Stop the answer that is being spoken.
  void interrupt() {
    _link?.send({'type': 'interrupt'});
    unawaited(_out?.stopNow());
    _outReady = null;
    _muted = true;
  }

  // ---------- what the server says ----------

  void _onMessage(Object message) {
    if (message is Uint8List) {
      final out = _out;
      if (out == null || _muted) return;
      _outReady ??= out.begin(_outRate);
      unawaited(_outReady!.then((_) => out.add(message)));
      return;
    }
    final e = message as Map<String, dynamic>;
    switch (e['type']) {
      case 'ready':
        _chatId = e['chat_id'] as String?;
        _outRate = (e['sample_rate_out'] as num? ?? 22050).toInt();
        if (_chatId != null && app.chatId != _chatId) {
          app.chatId = _chatId;
          unawaited(app.refreshChats());
        }
        unawaited(_openMicrophone());
      case 'speech_start':
        _set(VoiceStatus.hearing);
      case 'transcribing':
        _turnStarted();
      case 'no_speech':
        app.setWorking(null);
        _set(VoiceStatus.listening);
      case 'transcript':
        heard = e['text'] as String?;
        app.apply(ChatEvent('user', {'text': heard ?? '', 'voice': true}));
      case 'speaking':
        _muted = false; // a new sentence (an interrupt stops the server before the next one)
        _set(VoiceStatus.speaking);
      case 'interrupted':
        break;
      case 'turn_done':
        final out = _out;
        if (out != null) unawaited((_outReady ?? Future<void>.value()).then((_) => out.end()));
        _outReady = null;
        app.voiceTurn = false;
        app.setWorking(null);
        unawaited(app.refreshChats());
        _set(VoiceStatus.listening);
      case 'error' when e['code'] != null: // voice itself can't run
        final hint = e['hint'] as String? ?? '';
        unawaited(_fail(hint.isEmpty ? '${e['message']}' : '${e['message']} $hint'));
      case 'approval_answer' when app.pendingApproval == null: // a button: already in the chat
        break;
      default: // the agent's turn, exactly as in typed chat
        app.apply(ChatEvent.fromJson(e));
    }
  }

  Future<void> _openMicrophone() async {
    final session = _session;
    final mic = devices.microphone();
    _mic = mic;
    _out = devices.audioOut();
    try {
      final audio = await mic.start();
      if (session != _session) {
        unawaited(mic.stop()); // turned off while it opened
        return;
      }
      _micSub = audio.listen((pcm) {
        if (mode == VoiceMode.handsFree || talking) _link?.sendAudio(pcm);
      });
      _set(VoiceStatus.listening);
    } on MicrophoneError catch (e) {
      await _fail(e.message);
    }
  }

  void _onClosed() {
    if (on) unawaited(_fail('Voice connection closed.'));
  }

  /// Another chat was opened: voice belongs to the one it started in.
  void _onChat() {
    if (on && _chatId != null && app.chatId != _chatId) unawaited(stop());
  }

  Future<void> _fail(String message) async {
    _log.warning(message);
    await stop();
    error = message;
    notifyListeners();
  }

  /// A turn began (a question was heard, or a change answered): typing waits until it is done.
  void _turnStarted() {
    app.voiceTurn = true;
    app.setWorking('Thinking…');
    _set(VoiceStatus.thinking);
  }

  void _set(VoiceStatus s) {
    status = s;
    notifyListeners();
  }

  @override
  void notifyListeners() {
    if (!_disposed) super.notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    unawaited(stop());
    super.dispose();
  }
}
