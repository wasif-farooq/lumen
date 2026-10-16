import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';
import '../../core/models/json.dart';

/// Above the chat: its title and which model answers (and where it runs).
class ChatHeader extends StatelessWidget {
  const ChatHeader({super.key, required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final title = state.chats.where((c) => c.id == state.chatId).firstOrNull?.title ?? 'New chat';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14),
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: C.line))),
      child: Row(children: [
        Expanded(child: Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600), overflow: TextOverflow.ellipsis)),
        Container(
          height: 32,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(color: const Color(0xFF191D22), borderRadius: BorderRadius.circular(999), border: Border.all(color: C.line2)),
          child: Row(children: [
            StatusDot(size: 7, color: mapOf(state.status?['models'])['ollama_ok'] == true ? C.green : C.red),
            const SizedBox(width: 8),
            Text(state.model, style: monoStyle(size: 12.5, color: C.text2)),
            Text(' · ${state.agentProvider != 'Ollama' ? state.agentProvider : (state.cpuOnly ? 'CPU' : 'GPU')}',
                style: const TextStyle(fontSize: 13, color: C.text2)),
            if (state.agentCloud) ...[
              const SizedBox(width: 6),
              const Tooltip(message: 'Chat runs on a cloud service', child: Icon(Icons.cloud_outlined, size: 14, color: C.accent)),
            ],
          ]),
        ),
      ]),
    );
  }
}
