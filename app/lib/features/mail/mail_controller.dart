import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/app_state.dart';

/// The mailboxes and their sync status; checks again every few seconds while one is being read.
class MailController extends ChangeNotifier {
  MailController(this.api);
  final Api api;

  List<MailAccount> accounts = [];
  Object? loadError;
  bool loaded = false;
  Timer? _poll;
  bool _disposed = false;
  int _extraChecks = 0;

  static const pollEvery = Duration(seconds: 3);

  Future<void> load() async {
    try {
      accounts = await api.mailAccounts();
      loadError = null;
    } on ApiError catch (e) {
      loadError = e;
    }
    loaded = true;
    if (_disposed) return;
    notifyListeners();
    _poll?.cancel();
    final again = accounts.any((a) => a.syncing) || _extraChecks > 0;
    if (_extraChecks > 0) _extraChecks--;
    if (again) _poll = Timer(pollEvery, () => unawaited(load()));
  }

  Future<MailAccount> add(Map<String, Object> body) async {
    final a = await api.addMailAccount(body);
    await load();
    return a;
  }

  Future<void> remove(String id) async {
    await api.removeMailAccount(id);
    await load();
  }

  /// The server starts reading in a moment: keep checking for a few rounds so the change shows.
  Future<void> syncNow() async {
    await api.syncMail();
    _extraChecks = 3;
    await load();
  }

  @override
  void dispose() {
    _disposed = true;
    _poll?.cancel();
    super.dispose();
  }
}
