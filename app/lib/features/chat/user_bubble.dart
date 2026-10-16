import 'package:flutter/material.dart';

import '../../shared/theme.dart';
import 'copy.dart';

/// The user's message; a copy button appears on hover (desktop), long-press copies (phone).
class UserBubble extends StatefulWidget {
  const UserBubble({super.key, required this.text, required this.compact, this.image});
  final String text;
  final bool compact;
  final Widget? image; // a photo the user searched with

  @override
  State<UserBubble> createState() => _UserBubbleState();
}

class _UserBubbleState extends State<UserBubble> {
  bool hover = false;

  @override
  Widget build(BuildContext context) => MouseRegion(
        onEnter: (_) => setState(() => hover = true),
        onExit: (_) => setState(() => hover = false),
        child: Row(mainAxisAlignment: MainAxisAlignment.end, crossAxisAlignment: CrossAxisAlignment.center, children: [
          if (!widget.compact)
            AnimatedOpacity(opacity: hover ? 1 : 0, duration: const Duration(milliseconds: 120), child: CopyButton(text: widget.text)),
          const SizedBox(width: 4),
          Flexible(
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: widget.compact ? 300 : 560),
              child: GestureDetector(
                onLongPress: widget.compact ? () => copyText(context, widget.text) : null,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: const BoxDecoration(
                    color: C.bubble,
                    borderRadius: BorderRadius.only(topLeft: Radius.circular(14), topRight: Radius.circular(14), bottomLeft: Radius.circular(14), bottomRight: Radius.circular(4)),
                  ),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.end, mainAxisSize: MainAxisSize.min, children: [
                    if (widget.image != null) ...[
                      ClipRRect(borderRadius: BorderRadius.circular(8), child: SizedBox(width: 180, height: 130, child: widget.image)),
                      const SizedBox(height: 8),
                    ],
                    widget.compact ? Text(widget.text, style: const TextStyle(fontSize: 14.5)) : SelectableText(widget.text, style: const TextStyle(fontSize: 14.5)),
                  ]),
                ),
              ),
            ),
          ),
        ]),
      );
}
