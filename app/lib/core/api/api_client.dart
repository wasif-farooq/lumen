import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../logging/log.dart';
import 'api_error.dart';

final _log = Log('api');

/// HTTP to `lumen serve`: JSON in and out, timeouts, one retry for reads that found nobody
/// answering, and every failure turned into an [ApiError].
class ApiClient {
  ApiClient(this.base, {this.token, http.Client? client}) : httpClient = client ?? http.Client();

  final String base; // e.g. http://127.0.0.1:8765
  final String? token; // phones: the pairing token; the laptop needs none
  final http.Client httpClient;

  static const readTimeout = Duration(seconds: 20);
  static const writeTimeout = Duration(seconds: 30);

  Map<String, String> get headers => {
        'content-type': 'application/json',
        if (token != null) 'authorization': 'Bearer $token',
      };

  Uri uri(String path, [Map<String, String>? query]) => Uri.parse('$base$path').replace(queryParameters: query);

  Future<dynamic> getJson(String path, [Map<String, String>? query]) => _guard('GET', path, retry: true, () async {
        return decode(await httpClient.get(uri(path, query), headers: headers).timeout(readTimeout));
      });

  Future<dynamic> sendJson(String method, String path, [Object? body, Duration timeout = writeTimeout]) =>
      _guard(method, path, () async {
        final req = http.Request(method, uri(path))
          ..headers.addAll(headers)
          ..body = jsonEncode(body ?? {});
        return decode(await http.Response.fromStream(await httpClient.send(req).timeout(timeout)));
      });

  Future<dynamic> sendBytes(String path, List<int> bytes, {Duration timeout = const Duration(seconds: 60)}) =>
      _guard('POST', path, () async {
        final res = await httpClient
            .post(uri(path), headers: {...headers, 'content-type': 'application/octet-stream'}, body: bytes)
            .timeout(timeout);
        return decode(res);
      });

  /// Server-sent events: one JSON object per `data:` line.
  Stream<Map<String, dynamic>> postEvents(String path, Map<String, dynamic> payload) async* {
    final req = http.Request('POST', uri(path))
      ..headers.addAll(headers)
      ..body = jsonEncode(payload);
    final res = await _guard('POST', path, () => httpClient.send(req));
    if (res.statusCode >= 400) {
      throw _failed('POST', path, ApiError.fromResponse(res.statusCode, _json(await res.stream.bytesToString())));
    }
    try {
      await for (final line in res.stream.transform(utf8.decoder).transform(const LineSplitter())) {
        if (!line.startsWith('data: ')) continue;
        yield Map<String, dynamic>.from(jsonDecode(line.substring(6)) as Map);
      }
    } on FormatException catch (e) {
      throw _failed('POST', path, ApiError(kind: ApiErrorKind.badResponse, message: 'The answer was cut off or garbled.', cause: e));
    } on http.ClientException catch (e) {
      throw _failed('POST', path, _unreachable(e));
    }
  }

  dynamic decode(http.Response r) {
    final body = r.body.isEmpty ? null : _json(utf8.decode(r.bodyBytes));
    if (r.statusCode >= 400) throw ApiError.fromResponse(r.statusCode, body);
    return body;
  }

  Object? _json(String text) {
    try {
      return jsonDecode(text);
    } on FormatException {
      return text.isEmpty ? null : {'detail': text};
    }
  }

  Future<T> _guard<T>(String method, String path, Future<T> Function() call, {bool retry = false}) async {
    for (var attempt = 0;; attempt++) {
      try {
        return await call();
      } on ApiError catch (e) {
        throw _failed(method, path, e);
      } on TimeoutException catch (e) {
        throw _failed(method, path,
            ApiError(kind: ApiErrorKind.timeout, message: 'Lumen took too long to answer. Is it busy indexing?', cause: e));
      } on SocketException catch (e) {
        if (retry && attempt == 0) continue;
        throw _failed(method, path, _unreachable(e));
      } on http.ClientException catch (e) {
        if (retry && attempt == 0) continue;
        throw _failed(method, path, _unreachable(e));
      }
    }
  }

  ApiError _unreachable(Object cause) =>
      ApiError(kind: ApiErrorKind.unreachable, message: "Can't reach Lumen at $base.", cause: cause);

  ApiError _failed(String method, String path, ApiError e) {
    final where = '$method $path';
    if (e.isConnection || e.status >= 500) {
      _log.warning('$where failed: ${e.message}${e.id.isNotEmpty ? ' (id ${e.id})' : ''}', e.cause);
    } else {
      _log.info('$where: ${e.status} ${e.code} ${e.message}');
    }
    return e;
  }
}
