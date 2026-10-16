import '../api/api_error.dart';
import '../logging/log.dart';

final _log = Log('app');

/// What to tell people about an error: the server's own message when it sent one, never a raw
/// exception from inside the app (those go to the log, and the message says so).
String userMessage(Object error) => switch (error) {
      final ApiError e => e.message,
      _ => 'Something went wrong in the app. The details are in its log.',
    };

/// Log an error that isn't the server's answer (a bug in the app, a plugin failing…).
void logUnexpected(String where, Object error, [StackTrace? stack]) {
  if (error is ApiError) return; // already logged by the API client
  _log.error(where, error, stack);
}
