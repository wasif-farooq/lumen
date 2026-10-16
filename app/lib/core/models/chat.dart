import 'hit.dart';

/// A conversation in the sidebar.
class Chat {
  final String id;
  final String title;
  final double updated;

  Chat.fromJson(Map<String, dynamic> j)
      : id = j['id'] as String,
        title = j['title'] as String? ?? 'New chat',
        updated = (j['updated'] as num? ?? 0).toDouble();
}

/// An event in a conversation: what the user said, what the agent did, what it answered.
class ChatEvent {
  final String type; // user | tool_call | results | opened | approval | action_done | answer | error …
  final Map<String, dynamic> data;
  ChatEvent(this.type, this.data);

  factory ChatEvent.fromJson(Map<String, dynamic> j) => ChatEvent(j['type'] as String, j);

  String get text => data['text'] as String? ?? '';
  List<Hit> get hits => Hit.listFrom(data['hits']);
  String? get upload => data['upload'] as String?;
  String? get imagePath => data['image_path'] as String?;
}
