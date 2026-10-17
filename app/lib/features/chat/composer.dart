import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/photo_picker.dart';
import '../voice/voice_bar.dart';

/// Message box with send button.
class Composer extends StatefulWidget {
  const Composer({super.key, required this.state, this.compact = false});
  final AppState state;
  final bool compact;

  @override
  State<Composer> createState() => _ComposerState();
}

class _ComposerState extends State<Composer> {
  final _ctrl = TextEditingController();
  final _focus = FocusNode();

  Future<void> _attach() async {
    final bytes = await pickPhoto(context);
    if (bytes != null) unawaited(widget.state.findSimilar(photo: bytes));
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _send() {
    final text = _ctrl.text;
    if (text.trim().isEmpty || widget.state.busy || widget.state.voiceTurn || widget.state.pendingApproval != null) return;
    _ctrl.clear();
    unawaited(widget.state.send(text));
    _focus.requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    final busy = widget.state.busy || widget.state.voiceTurn;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 820),
        child: Padding(
          padding: EdgeInsets.fromLTRB(widget.compact ? 12 : 28, 0, widget.compact ? 12 : 28, widget.compact ? 12 : 10),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            VoiceBar(voice: widget.state.voice),
            Container(
              padding: const EdgeInsets.fromLTRB(16, 6, 6, 6),
              decoration: BoxDecoration(color: C.surface, borderRadius: BorderRadius.circular(16), border: Border.all(color: C.line2)),
              child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                Expanded(
                  child: CallbackShortcuts(
                    bindings: {const SingleActivator(LogicalKeyboardKey.enter): _send},
                    child: TextField(
                      controller: _ctrl,
                      focusNode: _focus,
                      autofocus: !widget.compact,
                      minLines: 1,
                      maxLines: 5,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => _send(),
                      style: const TextStyle(fontSize: 15),
                      decoration: InputDecoration(
                        hintText: widget.state.pendingApproval != null
                            ? 'Approve or cancel the change above first'
                            : (widget.compact ? 'Ask about your files…' : 'Ask to find, open or explain a file…'),
                        contentPadding: const EdgeInsets.symmetric(vertical: 12),
                      ),
                    ),
                  ),
                ),
                VoiceButton(voice: widget.state.voice),
                IconButton(
                  tooltip: 'Search with a photo',
                  onPressed: busy ? null : _attach,
                  icon: const Icon(Icons.add_photo_alternate_outlined, color: C.text2),
                ),
                const SizedBox(width: 4),
                IconButton.filled(
                  tooltip: 'Send',
                  onPressed: busy ? null : _send,
                  style: IconButton.styleFrom(
                    backgroundColor: C.accent,
                    foregroundColor: C.onAccent,
                    disabledBackgroundColor: C.raised,
                    minimumSize: const Size(44, 44),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  icon: busy
                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: C.text3))
                      : const Icon(Icons.arrow_upward_rounded),
                ),
              ]),
            ),
            if (!widget.compact)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                  Icon(widget.state.agentCloud || widget.state.visionCloud ? Icons.cloud_outlined : Icons.lock_outline,
                      size: 13, color: widget.state.agentCloud ? C.accent : C.muted),
                  const SizedBox(width: 6),
                  // Only promise privacy while it is true: a cloud provider sees what it is sent
                  Flexible(
                    child: Text(
                      widget.state.agentCloud
                          ? 'Chat runs on ${widget.state.agentProvider}: your questions and the files it reads are sent there.'
                          : widget.state.visionCloud
                              ? 'Chat runs on this laptop. Images are described by ${widget.state.visionProvider} while indexing.'
                              : 'Runs on this laptop. Nothing leaves it.',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 12, color: widget.state.agentCloud ? C.accent : C.muted),
                    ),
                  ),
                ]),
              ),
          ]),
        ),
      ),
    );
  }
}
