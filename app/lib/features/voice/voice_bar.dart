import 'dart:async';

import 'package:flutter/material.dart';

import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';
import 'voice_controller.dart';

/// The microphone button in the message box: turns voice chat on and off.
class VoiceButton extends StatelessWidget {
  const VoiceButton({super.key, required this.voice});
  final VoiceController voice;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: voice,
        builder: (context, _) => IconButton(
          tooltip: voice.on ? 'Turn voice off' : 'Talk to Lumen',
          onPressed: () => unawaited(voice.on ? voice.stop() : voice.start()),
          icon: Icon(voice.on ? Icons.mic : Icons.mic_none_outlined, color: voice.on ? C.accent : C.text2),
        ),
      );
}

/// Above the message box while voice chat is on: what is happening, what was heard, and the
/// controls (stop speaking, push-to-talk, hands-free).
class VoiceBar extends StatelessWidget {
  const VoiceBar({super.key, required this.voice});
  final VoiceController voice;

  static String describe(VoiceStatus s, VoiceMode mode, {required bool talking}) => switch (s) {
        VoiceStatus.off => '',
        VoiceStatus.connecting => 'Starting voice…',
        VoiceStatus.listening when mode == VoiceMode.pushToTalk && !talking => 'Hold the button and talk',
        VoiceStatus.listening => 'Listening…',
        VoiceStatus.hearing => 'Hearing you…',
        VoiceStatus.thinking => 'Thinking…',
        VoiceStatus.speaking => 'Speaking',
      };

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: voice,
        builder: (context, _) {
          if (!voice.on && voice.error == null) return const SizedBox.shrink();
          return Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.fromLTRB(14, 8, 8, 8),
            decoration: BoxDecoration(
              color: voice.error != null ? const Color(0xFF2A1A1A) : C.surface,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: voice.error != null ? const Color(0xFF4A2A2A) : C.line2),
            ),
            child: voice.error != null ? _error(context) : _status(context),
          );
        },
      );

  Widget _error(BuildContext context) => Row(children: [
        const Icon(Icons.mic_off_outlined, size: 18, color: C.red),
        const SizedBox(width: 10),
        Expanded(child: Text(voice.error!, style: const TextStyle(fontSize: 13, color: C.text2))),
        TextButton(onPressed: () => unawaited(voice.start()), child: const Text('Try again')),
      ]);

  Widget _status(BuildContext context) {
    final s = voice.status;
    final active = s == VoiceStatus.hearing || s == VoiceStatus.speaking || voice.talking;
    return Row(children: [
      StatusDot(color: active ? C.accent : (s == VoiceStatus.connecting ? C.muted : C.green), size: 9),
      const SizedBox(width: 10),
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
          Text(describe(s, voice.mode, talking: voice.talking), style: const TextStyle(fontWeight: FontWeight.w500)),
          if (voice.heard != null)
            Text('“${voice.heard}”',
                maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12.5, color: C.text3)),
        ]),
      ),
      if (s == VoiceStatus.speaking)
        TextButton.icon(onPressed: voice.interrupt, icon: const Icon(Icons.stop_rounded, size: 18), label: const Text('Stop')),
      if (voice.mode == VoiceMode.pushToTalk)
        GestureDetector(
          onTapDown: (_) => voice.pressTalk(),
          onTapUp: (_) => voice.releaseTalk(),
          onTapCancel: voice.releaseTalk,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
            decoration: BoxDecoration(
              color: voice.talking ? C.accent : C.raised,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text('Hold to talk',
                style: TextStyle(fontWeight: FontWeight.w600, color: voice.talking ? C.onAccent : C.text)),
          ),
        ),
      PopupMenuButton<VoiceMode>(
        tooltip: 'How to talk',
        initialValue: voice.mode,
        onSelected: voice.setMode,
        icon: const Icon(Icons.tune, size: 18, color: C.text3),
        itemBuilder: (_) => const [
          PopupMenuItem(value: VoiceMode.handsFree, child: Text('Hands-free: it hears when you stop')),
          PopupMenuItem(value: VoiceMode.pushToTalk, child: Text('Push to talk: hold a button')),
        ],
      ),
    ]);
  }
}
