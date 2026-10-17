import 'dart:async';

import 'package:flutter/material.dart';

import '../../shared/theme.dart';

/// The 6-digit code a phone types to pair, and how long it is valid.
class PairDialog extends StatefulWidget {
  const PairDialog({super.key, required this.code, required this.address, required this.lan});
  final String code, address;
  final bool lan;
  @override
  State<PairDialog> createState() => _PairDialogState();
}

class _PairDialogState extends State<PairDialog> {
  int left = 120;
  Timer? t;
  @override
  void initState() {
    super.initState();
    t = Timer.periodic(const Duration(seconds: 1), (_) {
      if (left <= 1) Navigator.of(context).maybePop();
      setState(() => left--);
    });
  }

  @override
  void dispose() {
    t?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Pair a phone'),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Open Lumen on your phone, pick this laptop, and enter:', style: TextStyle(color: C.text3)),
          const SizedBox(height: 18),
          Text(widget.code.split('').join(' '), style: monoStyle(size: 36, color: C.accent, weight: FontWeight.w500)),
          const SizedBox(height: 12),
          Text('Address: ${widget.address}', style: monoStyle(size: 13, color: C.text2)),
          const SizedBox(height: 6),
          Text('Code expires in $left s', style: const TextStyle(fontSize: 13, color: C.muted)),
          const SizedBox(height: 12),
          const Text('A paired phone can search and read the files in your indexed folders.',
              style: TextStyle(fontSize: 13, color: C.text3)),
          if (!widget.lan)
            const Padding(
              padding: EdgeInsets.only(top: 12),
              child: Text('The server is not on the network. Restart it with: lumen serve --lan', style: TextStyle(fontSize: 13, color: C.accent)),
            ),
        ]),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Done'))],
      );
}
