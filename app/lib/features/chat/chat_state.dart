import 'package:flutter/foundation.dart';

import '../../core/api/api.dart';
import '../../core/errors/errors.dart';
import '../../core/models/chat.dart';
import '../../core/models/hit.dart';
import 'tool_status.dart';

/// Conversations: the list, the open chat and its events, the selected file, and running a
/// turn of the agent. Part of AppState.
mixin ChatState on ChangeNotifier {
  Api get api;
  String get host;

  List<Chat> chats = [];
  String? chatId;
  List<ChatEvent> events = [];
  bool busy = false;
  bool voiceTurn = false; // a spoken turn is running: typing waits for it (approvals don't)
  String? working; // "Searching your files…" while the agent runs a tool
  Hit? selected;

  /// While voice chat is on, approvals go through it (so the result is spoken too).
  void Function(bool approved)? onApprove;

  Future<void> openChat(String id) async {
    chatId = id;
    selected = null;
    try {
      events = await api.events(id);
    } on ApiError catch (e) {
      events = [ChatEvent('error', {'text': 'Could not load this chat: ${e.message}'})];
    }
    final lastResults = events.where((e) => e.type == 'results' && e.hits.isNotEmpty).lastOrNull;
    selected = _firstFile(lastResults?.hits);
    notifyListeners();
  }

  void newChat() {
    chatId = null;
    events = [];
    selected = null;
    notifyListeners();
  }

  /// Delete a chat; throws ApiError when the server refuses (the caller shows it).
  Future<void> deleteChat(String id) async {
    await api.deleteChat(id);
    chats.removeWhere((c) => c.id == id);
    if (chatId == id) newChat();
    notifyListeners();
  }

  void select(Hit? hit) {
    selected = hit != null && hit.isMail ? null : hit;
    notifyListeners();
  }

  /// The result shown in the preview panel: a file (a mail opens in the viewer instead).
  static Hit? _firstFile(List<Hit>? hits) => hits?.where((h) => !h.isMail).firstOrNull;

  /// The change the agent is waiting on (Approve / Cancel), if any.
  ChatEvent? get pendingApproval {
    for (final e in events.reversed) {
      if (e.type == 'approval_answer') return null;
      if (e.type == 'approval') return e;
    }
    return null;
  }

  Future<void> answerApproval(bool approved) async {
    if (busy || chatId == null || pendingApproval == null) return;
    events.add(ChatEvent('approval_answer', {'approved': approved}));
    final voice = onApprove;
    if (voice != null) {
      voice(approved);
      notifyListeners();
      return;
    }
    await _run(() => api.approve(chatId!, approved), approved ? 'Making the change…' : 'Cancelling…');
  }

  Future<void> undo(String actionId) async {
    try {
      final msg = await api.undo(actionId, chatId);
      events.add(ChatEvent('undone', {'action_id': actionId, 'text': msg}));
    } on Object catch (e, st) {
      logUnexpected('undo', e, st);
      events.add(ChatEvent('error', {'text': 'Could not undo: ${userMessage(e)}'}));
    }
    notifyListeners();
  }

  Future<void> send(String text) async {
    text = text.trim();
    if (text.isEmpty || busy || voiceTurn || pendingApproval != null) return;
    await _run(() async* {
      chatId ??= (await api.newChat()).id;
      events.add(ChatEvent('user', {'text': text}));
      notifyListeners();
      yield* api.send(chatId!, text);
    }, 'Thinking…');
  }

  Future<void> _run(Stream<ChatEvent> Function() start, String status) async {
    busy = true;
    working = status;
    notifyListeners();
    try {
      await for (final e in start()) {
        apply(e);
      }
      chats = await api.chats();
    } on Object catch (e, st) {
      logUnexpected('chat turn', e, st);
      final lost = e is ApiError && e.isConnection;
      events.add(ChatEvent('error', {'text': lost ? 'Lost connection to $host. ${e.message}' : userMessage(e)}));
    } finally {
      busy = false;
      working = null;
      notifyListeners();
    }
  }

  /// Reload the chat list (titles change after the first message).
  Future<void> refreshChats() async {
    try {
      chats = await api.chats();
      notifyListeners();
    } on ApiError {
      // logged by the API client; the list stays as it was
    }
  }

  /// Add one event of an agent turn to the open chat (typed turns, and voice turns as they come).
  void apply(ChatEvent e) {
    switch (e.type) {
      case 'started':
      case 'done':
        break;
      case 'tool_call': // kept in the history; shown only as the status line while it runs
        working = '${toolStatus(e.data['name'] as String? ?? '', Map<String, dynamic>.from(e.data['args'] as Map? ?? {}))}…';
        events.add(e);
      case 'results':
        events.add(e);
        if (e.hits.isNotEmpty) selected = _firstFile(e.hits);
        working = 'Thinking…';
      default:
        events.add(e);
    }
    notifyListeners();
  }

  /// Show (or clear) what is happening, e.g. "Listening…" during a voice turn.
  void setWorking(String? text) {
    working = text;
    notifyListeners();
  }

  /// "Find similar" on an image result, or a dropped/attached photo: results go into the chat.
  Future<void> findSimilar({String? path, Uint8List? photo}) async {
    if (busy || voiceTurn) return;
    busy = true;
    working = 'Looking for similar images…';
    notifyListeners();
    try {
      chatId ??= (await api.newChat()).id;
      if (photo != null) {
        await api.chatSimilarUpload(chatId!, photo);
      } else {
        await api.chatSimilar(chatId!, path!);
      }
      events = await api.events(chatId!);
      final last = events.where((e) => e.type == 'results').lastOrNull;
      selected = (last == null || last.hits.isEmpty) ? selected : _firstFile(last.hits);
      chats = await api.chats();
    } on Object catch (e, st) {
      logUnexpected('find similar', e, st);
      events.add(ChatEvent('error', {'text': 'Could not search images: ${userMessage(e)}'}));
    } finally {
      busy = false;
      working = null;
      notifyListeners();
    }
  }
}
