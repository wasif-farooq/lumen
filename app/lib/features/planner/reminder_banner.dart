import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';

/// Above the message box: reminders that went off and wait for the user (Done, or Snooze 10 min).
class ReminderBanner extends StatelessWidget {
  const ReminderBanner({super.key, required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final due = state.dueReminders;
    if (due.isEmpty) return const SizedBox.shrink();
    return Column(children: [
      for (final r in due.take(3))
        Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.fromLTRB(14, 6, 6, 6),
          decoration: BoxDecoration(
            color: C.accentSoft,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFF4A3A20)),
          ),
          child: Row(children: [
            const Icon(Icons.alarm, size: 18, color: C.accent),
            const SizedBox(width: 10),
            Expanded(
              child: Text(r.text, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w500)),
            ),
            TextButton(onPressed: () => unawaited(state.snoozeReminder(r)), child: const Text('Snooze 10 min')),
            FilledButton.tonal(onPressed: () => unawaited(state.reminderDone(r)), child: const Text('Done')),
          ]),
        ),
      if (due.length > 3)
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Text('and ${due.length - 3} more', style: const TextStyle(color: C.text3, fontSize: 12.5)),
        ),
    ]);
  }
}
