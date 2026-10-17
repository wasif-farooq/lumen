import 'package:flutter/foundation.dart';

import '../features/chat/chat_state.dart';
import '../features/voice/voice_controller.dart';
import 'api/api.dart';
import 'errors/errors.dart';

export 'api/api.dart';
export 'models/chat.dart';
export 'models/file_info.dart';
export 'models/hit.dart';

/// The app's connection to one laptop: its status, and the conversations (ChatState),
/// shared by desktop and mobile.
class AppState extends ChangeNotifier with ChatState {
  AppState(this.api, {VoiceDevices? voiceDevices}) {
    voice = VoiceController(this, devices: voiceDevices);
  }

  /// Talking to Lumen (off until the microphone button is pressed).
  late final VoiceController voice;

  @override
  Api api;
  Map<String, dynamic>? status;
  String? connectError;

  @override
  String get host => status?['host'] as String? ?? 'laptop';
  Map<String, dynamic> get _models => Map<String, dynamic>.from(status?['models'] as Map? ?? const {});
  String get model => _models['agent'] as String? ?? '';
  bool get cpuOnly => _models['cpu_only'] == true;
  String get agentProvider => _models['agent_provider'] as String? ?? 'Ollama';
  bool get agentCloud => _models['agent_cloud'] == true;
  String get visionProvider => _models['vision_provider'] as String? ?? 'Ollama';
  bool get visionCloud => _models['vision_cloud'] == true;

  Future<bool> connect() async {
    try {
      status = await api.status();
      chats = await api.chats();
      connectError = null;
      notifyListeners();
      return true;
    } on Object catch (e, st) {
      logUnexpected('connect', e, st);
      connectError = userMessage(e);
      notifyListeners();
      return false;
    }
  }

  /// Refresh what the sidebar and settings show; a failed refresh keeps the last status.
  Future<void> refreshStatus() async {
    try {
      status = await api.status();
      notifyListeners();
    } on ApiError {
      // logged by the API client; the next refresh tries again
    }
  }
}
