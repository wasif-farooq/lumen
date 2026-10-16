import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_error.dart';
import '../../core/errors/errors.dart';
import '../theme.dart';

/// A failed action: one line, and Details when the server gave a hint or a request id.
/// Takes the messenger and navigator (not a context), so it works after an `await`.
void showErrorSnack(ScaffoldMessengerState messenger, NavigatorState navigator, String text, [ApiError? error]) {
  final more = error != null && (error.hint.isNotEmpty || error.id.isNotEmpty);
  messenger.showSnackBar(SnackBar(
    content: Text(text),
    action: more
        ? SnackBarAction(
            label: 'Details',
            onPressed: () => showDialog<void>(context: navigator.context, builder: (_) => ErrorDetailsDialog(error: error)),
          )
        : null,
  ));
}

/// What the server said about a failure: message, what to try, and the id to look up in its log.
class ErrorDetailsDialog extends StatelessWidget {
  const ErrorDetailsDialog({super.key, required this.error});
  final ApiError error;

  @override
  Widget build(BuildContext context) => AlertDialog(
        icon: const Icon(Icons.error_outline, color: C.red),
        title: const Text('What went wrong'),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(error.message),
          if (error.hint.isNotEmpty) ...[const SizedBox(height: 10), Text(error.hint, style: const TextStyle(color: C.text3))],
          if (error.id.isNotEmpty) ...[
            const SizedBox(height: 14),
            SelectableText('Request id ${error.id} (the server log has the details)', style: monoStyle(size: 12.5, color: C.muted)),
          ],
        ]),
        actions: [
          if (error.id.isNotEmpty)
            TextButton(
              onPressed: () => Clipboard.setData(ClipboardData(text: 'Lumen error ${error.code} id ${error.id}: ${error.message}')),
              child: const Text('Copy'),
            ),
          FilledButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
        ],
      );
}

/// Something that didn't load: why, and a way to try again.
class ErrorCard extends StatelessWidget {
  const ErrorCard({super.key, required this.error, this.title = "Couldn't load this", this.onRetry});
  final Object error;
  final String title;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final api = error is ApiError ? error as ApiError : null;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF2A1A1A),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF4A2A2A)),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Icon(Icons.error_outline, size: 18, color: C.red),
        const SizedBox(width: 10),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 2),
            Text(userMessage(error), style: const TextStyle(fontSize: 13, color: C.text3)),
            if (api != null && api.hint.isNotEmpty) Text(api.hint, style: const TextStyle(fontSize: 13, color: C.muted)),
          ]),
        ),
        if (onRetry != null) TextButton(onPressed: onRetry, child: const Text('Retry')),
      ]),
    );
  }
}
