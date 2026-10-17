import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:web_socket_channel/io.dart';

import 'api.dart';

/// The voice connection: JSON events and spoken audio from the server; microphone audio and
/// control messages (stop, interrupt, approve) to it. Protocol: docs/VOICE.md.
abstract class VoiceLink {
  /// Events (Map) and audio (Uint8List), in the order the server sent them.
  Stream<Object> get incoming;
  void sendAudio(Uint8List pcm);
  void send(Map<String, Object?> message);
  Future<void> close();
}

class WebSocketVoiceLink implements VoiceLink {
  WebSocketVoiceLink._(this._channel);
  final IOWebSocketChannel _channel;

  /// Connect to `lumen serve`, continuing [chatId] (or a new chat when null).
  static Future<VoiceLink> connect(Api api, String? chatId) async {
    final base = Uri.parse(api.base);
    final uri = base.replace(
      scheme: base.scheme == 'https' ? 'wss' : 'ws',
      path: '/api/voice',
      queryParameters: {'chat_id': ?chatId},
    );
    final channel = IOWebSocketChannel.connect(uri, headers: api.headers, connectTimeout: const Duration(seconds: 10));
    try {
      await channel.ready;
    } on Object catch (e) {
      throw ApiError(kind: ApiErrorKind.unreachable, message: "Can't reach Lumen at ${api.base} for voice.", cause: e);
    }
    return WebSocketVoiceLink._(channel);
  }

  @override
  Stream<Object> get incoming => _channel.stream.map((m) => m is String
      ? Map<String, dynamic>.from(jsonDecode(m) as Map)
      : Uint8List.fromList(m as List<int>));

  @override
  void sendAudio(Uint8List pcm) => _channel.sink.add(pcm);

  @override
  void send(Map<String, Object?> message) => _channel.sink.add(jsonEncode(message));

  @override
  Future<void> close() => _channel.sink.close();

  /// Why the server closed the connection, when it says (4401 not paired, 4404 no such chat).
  int? get closeCode => _channel.closeCode;
}
