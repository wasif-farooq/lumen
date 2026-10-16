import 'package:flutter/material.dart';

import '../../shared/widgets/error_views.dart';
import '../api/api_error.dart';
import 'errors.dart';

/// Run an action the user started; if it fails, say so in a snackbar (with Details when the
/// server said more) and return null. On success, show `success` (if given) and return the result.
Future<T?> runGuarded<T>(
  BuildContext context,
  Future<T> Function() action, {
  required String failure,
  String Function(T result)? success,
}) async {
  final messenger = ScaffoldMessenger.of(context);
  final navigator = Navigator.of(context);
  try {
    final result = await action();
    final done = success?.call(result);
    if (done != null && done.isNotEmpty) messenger.showSnackBar(SnackBar(content: Text(done)));
    return result;
  } on Object catch (e, st) {
    logUnexpected(failure, e, st);
    showErrorSnack(messenger, navigator, '$failure: ${userMessage(e)}', e is ApiError ? e : null);
    return null;
  }
}
