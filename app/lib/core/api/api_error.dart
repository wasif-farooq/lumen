/// Why a request to the Lumen server failed, in words the app can show.
enum ApiErrorKind {
  /// Nothing answered (server not running, wrong address, no network).
  unreachable,

  /// It answered too slowly.
  timeout,

  /// It answered with an error ({"error": {code, message, hint, id}}).
  server,

  /// It answered with something that isn't what the app expects.
  badResponse,
}

class ApiError implements Exception {
  ApiError({
    required this.kind,
    required this.message,
    this.status = 0,
    this.code = '',
    this.hint = '',
    this.id = '',
    this.cause,
  });

  final ApiErrorKind kind;
  final int status; // HTTP status; 0 when there was no answer
  final String code; // e.g. not_found, local_only, internal
  final String message, hint;
  final String id; // the server's request id: the same id is in its log
  final Object? cause;

  /// The server's error answer (new shape, or the older {"detail": …}).
  factory ApiError.fromResponse(int status, Object? body) {
    if (body is Map) {
      final e = body['error'];
      if (e is Map) {
        return ApiError(
          kind: ApiErrorKind.server,
          status: status,
          code: '${e['code'] ?? ''}',
          message: '${e['message'] ?? 'HTTP $status'}',
          hint: '${e['hint'] ?? ''}',
          id: '${e['id'] ?? ''}',
        );
      }
      return ApiError(kind: ApiErrorKind.server, status: status, message: '${body['detail'] ?? body}');
    }
    return ApiError(kind: ApiErrorKind.server, status: status, message: 'HTTP $status');
  }

  bool get isUnexpected => kind == ApiErrorKind.badResponse || status >= 500 && code == 'internal';
  bool get isConnection => kind == ApiErrorKind.unreachable || kind == ApiErrorKind.timeout;

  @override
  String toString() => message;
}
