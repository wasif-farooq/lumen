import '../models/file_info.dart';
import '../models/hit.dart';
import 'api_client.dart';

/// Searching, previews and opening files on the laptop.
mixin FilesApi on ApiClient {
  Future<List<Hit>> search(String q, {String ext = ''}) async => Hit.listFrom(await getJson('/api/search', {'q': q, 'ext': ext}));
  Future<FileInfo> file(String path, {double? at}) async =>
      FileInfo(Map<String, dynamic>.from(await getJson('/api/file', {'path': path, if (at != null) 'at': '$at'}) as Map));
  String thumbUrl(String path, {int w = 480, double? t}) =>
      uri('/api/thumb', {'path': path, 'w': '$w', if (t != null) 't': '$t'}).toString();
  Future<String> open(String path, {double start = 0}) async =>
      _message(await sendJson('POST', '/api/open', {'path': path, 'start_seconds': start}));
  Future<String> show(String path) async => _message(await sendJson('POST', '/api/show', {'path': path}));

  String _message(Object? r) => r is Map ? r['message'] as String? ?? '' : '';
}
