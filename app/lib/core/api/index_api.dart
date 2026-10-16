import 'api_client.dart';

/// Index runs, indexed folders and what is kept out of the index.
mixin IndexApi on ApiClient {
  Future<void> runIndex() => sendJson('POST', '/api/index');
  Future<void> stopIndex() => sendJson('POST', '/api/index/stop');
  Future<void> pauseIndex() => sendJson('POST', '/api/index/pause');
  Future<void> resumeIndex() => sendJson('POST', '/api/index/resume');
  Future<Map<String, dynamic>> indexProgress() async => Map<String, dynamic>.from(await getJson('/api/index') as Map);

  Future<int> excludePath(String path) async => _removed(await sendJson('POST', '/api/index/exclude', {'path': path}));
  Future<void> includePath(String path) => sendJson('POST', '/api/index/include', {'path': path, 'reindex': true});
  Future<void> pauseFolder(String path) => sendJson('POST', '/api/folders/pause', {'path': path});
  Future<void> resumeFolder(String path) => sendJson('POST', '/api/folders/resume', {'path': path, 'reindex': true});
  Future<int> clearFolder(String path, {bool reindex = false}) async =>
      _removed(await sendJson('POST', '/api/folders/clear', {'path': path, 'reindex': reindex}));

  int _removed(Object? r) => r is Map ? (r['removed'] as num? ?? 0).toInt() : 0;
}
