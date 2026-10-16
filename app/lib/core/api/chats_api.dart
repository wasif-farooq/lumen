import 'dart:typed_data';

import '../models/chat.dart';
import '../models/hit.dart';
import 'api_client.dart';

/// Conversations with the agent, approvals and undo, and searching by picture.
mixin ChatsApi on ApiClient {
  Future<List<Chat>> chats() async =>
      [for (final c in await getJson('/api/chats') as List) Chat.fromJson(Map<String, dynamic>.from(c as Map))];
  Future<Chat> newChat() async => Chat.fromJson(Map<String, dynamic>.from(await sendJson('POST', '/api/chats') as Map));
  Future<void> deleteChat(String id) => sendJson('DELETE', '/api/chats/$id');
  Future<List<ChatEvent>> events(String chatId) async => [
        for (final e in await getJson('/api/chats/$chatId/events') as List) ChatEvent.fromJson(Map<String, dynamic>.from(e as Map)),
      ];

  /// Streams the agent's events for one message.
  Stream<ChatEvent> send(String chatId, String text) =>
      postEvents('/api/chats/$chatId/messages', {'text': text}).map(ChatEvent.fromJson);

  /// Approve or cancel the change the agent is waiting on; streams what happens next.
  Stream<ChatEvent> approve(String chatId, bool approved) =>
      postEvents('/api/chats/$chatId/approve', {'approved': approved}).map(ChatEvent.fromJson);

  Future<String> undo(String actionId, String? chatId) async =>
      ((await sendJson('POST', '/api/actions/$actionId/undo', {'chat_id': chatId}) as Map)['message'] as String?) ?? '';

  Future<List<Hit>> imageSearch(String q) async => Hit.listFrom(await getJson('/api/images/search', {'q': q}));
  Future<void> chatSimilar(String chatId, String path) => sendJson('POST', '/api/chats/$chatId/similar', {'path': path});
  Future<void> chatSimilarUpload(String chatId, Uint8List bytes) => sendBytes('/api/chats/$chatId/similar-upload', bytes);
  String uploadUrl(String id) => uri('/api/uploads/$id').toString();
}
