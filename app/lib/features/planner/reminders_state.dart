import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/api/api.dart';
import '../../core/models/planner.dart';

/// Reminders that went off and wait for the user: the banner above the message box. Checked every
/// 30 s once the app is connected (the server also shows a desktop notification). Part of AppState.
mixin RemindersState on ChangeNotifier {
  Api get api;

  List<Reminder> dueReminders = [];
  Timer? _reminderWatch;

  void watchReminders() {
    _reminderWatch ??= Timer.periodic(const Duration(seconds: 30), (_) => unawaited(refreshReminders()));
    unawaited(refreshReminders());
  }

  void stopWatchingReminders() {
    _reminderWatch?.cancel();
    _reminderWatch = null;
  }

  Future<void> refreshReminders() async {
    try {
      dueReminders = await api.dueReminders();
      notifyListeners();
    } on ApiError {
      // logged by the API client; the next check tries again
    }
  }

  /// Done: off the banner (a repeating reminder still comes back at its next time).
  Future<void> reminderDone(Reminder r) async {
    dueReminders = [for (final x in dueReminders) if (x.id != r.id) x];
    notifyListeners();
    await api.acknowledgeReminder(r.id);
  }

  Future<void> snoozeReminder(Reminder r, {int minutes = 10}) async {
    dueReminders = [for (final x in dueReminders) if (x.id != r.id) x];
    notifyListeners();
    await api.snoozeReminder(r.id, minutes: minutes);
  }
}
