import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api.dart';
import '../../core/errors/errors.dart';
import '../../core/models/json.dart';
import '../../shared/theme.dart';

/// Tries a model on a job and shows what passed. While choosing: "Use this model" when it works,
/// "Pick another" or "Use anyway" when it doesn't. Pops 'use', 'another' or null.
class CheckDialog extends StatefulWidget {
  const CheckDialog({super.key, required this.api, required this.role, required this.title, required this.provider, required this.model, this.choosing = false, this.onResult});
  final Api api;
  final String role, title, provider, model;
  final bool choosing;
  final ValueChanged<Map<String, dynamic>>? onResult;
  @override
  State<CheckDialog> createState() => _CheckDialogState();
}

class _CheckDialogState extends State<CheckDialog> {
  Map<String, dynamic>? result;
  String? error;

  @override
  void initState() {
    super.initState();
    unawaited(_run());
  }

  Future<void> _run() async {
    try {
      final r = {...await widget.api.checkModel(widget.role, widget.provider, widget.model), 'model': widget.model};
      widget.onResult?.call(r);
      if (mounted) setState(() => result = r);
    } on Object catch (e, st) {
      logUnexpected('model check', e, st);
      if (mounted) setState(() => error = userMessage(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = result;
    final ok = r?['ok'] == true;
    final job = widget.role == 'agent' ? 'chat' : 'images & video';
    return AlertDialog(
      icon: r == null && error == null
          ? const SizedBox(width: 28, height: 28, child: CircularProgressIndicator(strokeWidth: 3, color: C.accent))
          : Icon(ok ? Icons.verified_outlined : Icons.error_outline, color: ok ? C.green : C.red, size: 30),
      title: Text(r == null && error == null
          ? 'Checking ${widget.model}…'
          : ok
              ? '${widget.model} works for $job'
              : '${widget.model} may not work for $job'),
      content: SizedBox(
        width: 460,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (r == null && error == null)
            Text(
              widget.role == 'agent'
                  ? 'Asking it to search your files, to see that it calls tools. A local model may take a minute to load.'
                  : 'Showing it a test picture, to see that it reads images. A local model may take a minute to load.',
              style: const TextStyle(color: C.text3),
            ),
          if (error != null) Text(error!, style: const TextStyle(color: C.red)),
          if (r != null) ...[
            for (final c in listOf(r['checks']))
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(c['ok'] == true ? Icons.check_circle : Icons.cancel, size: 18, color: c['ok'] == true ? C.green : C.red),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${c['name']}', style: const TextStyle(fontWeight: FontWeight.w500)),
                      Text('${c['detail']}', style: const TextStyle(fontSize: 13, color: C.text3)),
                    ]),
                  ),
                ]),
              ),
            Text('Took ${r['seconds']} s', style: const TextStyle(fontSize: 12.5, color: C.muted)),
          ],
        ]),
      ),
      actions: [
        if (r == null && error == null)
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel'))
        else if (!widget.choosing)
          FilledButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))
        else if (ok)
          FilledButton(onPressed: () => Navigator.pop(context, 'use'), child: const Text('Use this model'))
        else ...[
          TextButton(onPressed: () => Navigator.pop(context, 'use'), child: const Text('Use anyway')),
          FilledButton(onPressed: () => Navigator.pop(context, 'another'), child: const Text('Pick another')),
        ],
      ],
    );
  }
}
