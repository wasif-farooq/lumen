import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../shared/theme.dart';

/// Copies a message as plain text (markdown markers removed) and confirms it.
Future<void> copyText(BuildContext context, String text) async {
  final plain = text.replaceAll('**', '').replaceAll('`', '');
  await Clipboard.setData(ClipboardData(text: plain));
  if (context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Copied'), duration: Duration(seconds: 1)));
  }
}

class CopyButton extends StatefulWidget {
  const CopyButton({super.key, required this.text});
  final String text;

  @override
  State<CopyButton> createState() => _CopyButtonState();
}

class _CopyButtonState extends State<CopyButton> {
  bool copied = false;

  @override
  Widget build(BuildContext context) => IconButton(
        tooltip: copied ? 'Copied' : 'Copy',
        visualDensity: VisualDensity.compact,
        iconSize: 16,
        onPressed: () async {
          await Clipboard.setData(ClipboardData(text: widget.text.replaceAll('**', '').replaceAll('`', '')));
          setState(() => copied = true);
          await Future.delayed(const Duration(milliseconds: 1500));
          if (mounted) setState(() => copied = false);
        },
        icon: Icon(copied ? Icons.check : Icons.content_copy_outlined, color: copied ? C.green : C.muted),
      );
}
