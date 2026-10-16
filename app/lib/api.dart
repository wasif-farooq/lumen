import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

/// One search hit / file result from the agent.
class Hit {
  final String path, name, ext, kind, snippet, atText;
  final int size;
  final double mtime;
  final double? duration, at;

  Hit.fromJson(Map<String, dynamic> j)
      : path = j['path'] ?? '',
        name = j['name'] ?? '',
        ext = j['ext'] ?? '',
        kind = j['kind'] ?? 'file',
        snippet = j['snippet'] ?? '',
        atText = j['at_text'] ?? '',
        size = (j['size'] ?? 0) as int,
        mtime = (j['mtime'] ?? 0).toDouble(),
        duration = (j['duration'] as num?)?.toDouble(),
        at = (j['at'] as num?)?.toDouble();

  String get folder => path.substring(0, path.lastIndexOf('/').clamp(0, path.length));
  bool get isMedia => kind == 'video' || kind == 'audio';
}

class Chat {
  final String id;
  final String title;
  final double updated;
  Chat.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        title = j['title'] ?? 'New chat',
        updated = (j['updated'] ?? 0).toDouble();
}

/// An event in a conversation: what the user said, what the agent did, what it answered.
class ChatEvent {
  final String type; // user | tool_call | results | opened | answer | error
  final Map<String, dynamic> data;
  ChatEvent(this.type, this.data);

  String get text => data['text'] ?? '';
  List<Hit> get hits => [for (final h in (data['hits'] as List? ?? [])) Hit.fromJson(h)];
  List<DupGroup> get groups => [for (final g in (data['groups'] as List? ?? [])) DupGroup.fromJson(g)];
  String? get upload => data['upload'];
  String? get imagePath => data['image_path'];
}

/// Copies of the same image: identical files, or the same picture saved differently.
class DupGroup {
  final String kind, keep;
  final int reclaimable;
  final List<Hit> files;
  DupGroup.fromJson(Map<String, dynamic> j)
      : kind = j['kind'] ?? 'identical',
        keep = j['keep'] ?? '',
        reclaimable = (j['reclaimable'] ?? 0) as int,
        files = [for (final f in (j['files'] as List? ?? [])) Hit.fromJson({...f, 'kind': 'image'})];
  bool get identical => kind == 'identical';
}

class Segment {
  final double start;
  final String text, time;
  Segment.fromJson(Map<String, dynamic> j)
      : start = (j['start'] as num).toDouble(),
        text = j['text'] ?? '',
        time = j['time'] ?? '';
}

class FileInfo {
  final Map<String, dynamic> j;
  FileInfo(this.j);
  String get path => j['path'];
  String get name => j['name'];
  String get kind => j['kind'];
  String get folder => j['folder'];
  String get caption => j['caption'] ?? '';
  String get excerpt => j['excerpt'] ?? '';
  int get size => j['size'] ?? 0;
  double get mtime => (j['mtime'] ?? 0).toDouble();
  double? get duration => (j['duration'] as num?)?.toDouble();
  bool get searchable => j['searchable'] == true;
  List<Segment> get segments => [for (final s in (j['segments'] as List? ?? [])) Segment.fromJson(s)];
}

class ApiException implements Exception {
  final int status;
  final String message;
  ApiException(this.status, this.message);
  @override
  String toString() => message;
}

/// Talks to `lumen serve`. On the laptop: no token. Phones: a paired token.
class Api {
  final String base; // e.g. http://127.0.0.1:8765
  final String? token;
  final http.Client _http;

  Api(this.base, {this.token, http.Client? client}) : _http = client ?? http.Client();

  Map<String, String> get headers => {
        'content-type': 'application/json',
        if (token != null) 'authorization': 'Bearer $token',
      };

  Uri _u(String path, [Map<String, String>? q]) => Uri.parse('$base$path').replace(queryParameters: q);

  Future<dynamic> _get(String path, [Map<String, String>? q]) async =>
      _decode(await _http.get(_u(path, q), headers: headers).timeout(const Duration(seconds: 20)));

  Future<dynamic> _send(String method, String path, [Object? body, Duration timeout = const Duration(seconds: 30)]) async {
    final req = http.Request(method, _u(path))
      ..headers.addAll(headers)
      ..body = jsonEncode(body ?? {});
    final res = await http.Response.fromStream(await _http.send(req).timeout(timeout));
    return _decode(res);
  }

  dynamic _decode(http.Response r) {
    final body = r.body.isEmpty ? null : jsonDecode(utf8.decode(r.bodyBytes));
    if (r.statusCode >= 400) {
      throw ApiException(r.statusCode, body is Map ? '${body['detail'] ?? body}' : 'HTTP ${r.statusCode}');
    }
    return body;
  }

  Future<Map<String, dynamic>> hello() async => await _get('/api/hello');
  Future<Map<String, dynamic>> status() async => await _get('/api/status');

  Future<List<Chat>> chats() async => [for (final c in await _get('/api/chats')) Chat.fromJson(c)];
  Future<Chat> newChat() async => Chat.fromJson(await _send('POST', '/api/chats'));
  Future<void> deleteChat(String id) => _send('DELETE', '/api/chats/$id');
  Future<List<ChatEvent>> events(String chatId) async => [
        for (final e in await _get('/api/chats/$chatId/events')) ChatEvent(e['type'], Map<String, dynamic>.from(e)),
      ];

  /// Streams the agent's events (server-sent events) for one message.
  Stream<ChatEvent> send(String chatId, String text) => _stream('/api/chats/$chatId/messages', {'text': text});

  Stream<ChatEvent> _stream(String path, Map<String, dynamic> payload) async* {
    final req = http.Request('POST', _u(path))
      ..headers.addAll(headers)
      ..body = jsonEncode(payload);
    final res = await _http.send(req);
    if (res.statusCode >= 400) {
      throw ApiException(res.statusCode, await res.stream.bytesToString());
    }
    await for (final line in res.stream.transform(utf8.decoder).transform(const LineSplitter())) {
      if (!line.startsWith('data: ')) continue;
      final j = jsonDecode(line.substring(6)) as Map<String, dynamic>;
      yield ChatEvent(j['type'], j);
    }
  }

  /// Approve or cancel the change the agent is waiting on; streams what happens next.
  Stream<ChatEvent> approve(String chatId, bool approved) => _stream('/api/chats/$chatId/approve', {'approved': approved});
  Future<String> undo(String actionId, String? chatId) async =>
      (await _send('POST', '/api/actions/$actionId/undo', {'chat_id': chatId}))['message'] ?? '';

  Future<List<Hit>> imageSearch(String q) async => [for (final h in await _get('/api/images/search', {'q': q})) Hit.fromJson(h)];
  Future<void> chatSimilar(String chatId, String path) => _send('POST', '/api/chats/$chatId/similar', {'path': path});
  Future<void> chatSimilarUpload(String chatId, Uint8List bytes) async {
    final res = await _http
        .post(_u('/api/chats/$chatId/similar-upload'), headers: {...headers, 'content-type': 'application/octet-stream'}, body: bytes)
        .timeout(const Duration(seconds: 60));
    _decode(res);
  }

  String uploadUrl(String id) => _u('/api/uploads/$id').toString();
  Future<List<DupGroup>> duplicates() async =>
      [for (final g in (await _get('/api/duplicates'))['groups'] as List) DupGroup.fromJson(g)];

  Future<List<Hit>> search(String q, {String ext = ''}) async =>
      [for (final h in await _get('/api/search', {'q': q, 'ext': ext})) Hit.fromJson(h)];
  Future<FileInfo> file(String path, {double? at}) async =>
      FileInfo(await _get('/api/file', {'path': path, if (at != null) 'at': '$at'}));
  String thumbUrl(String path, {int w = 480, double? t}) =>
      _u('/api/thumb', {'path': path, 'w': '$w', if (t != null) 't': '$t'}).toString();
  Future<String> open(String path, {double start = 0}) async =>
      (await _send('POST', '/api/open', {'path': path, 'start_seconds': start}))['message'] ?? '';
  Future<String> show(String path) async => (await _send('POST', '/api/show', {'path': path}))['message'] ?? '';

  Future<Map<String, dynamic>> settings() async => await _get('/api/settings');
  Future<Map<String, dynamic>> saveSettings(Map<String, dynamic> s) async => await _send('PUT', '/api/settings', s);
  Future<void> runIndex() => _send('POST', '/api/index');
  Future<void> stopIndex() => _send('POST', '/api/index/stop');
  Future<void> pauseIndex() => _send('POST', '/api/index/pause');
  Future<void> resumeIndex() => _send('POST', '/api/index/resume');
  Future<int> excludePath(String path) async => (await _send('POST', '/api/index/exclude', {'path': path}))['removed'] ?? 0;
  Future<void> includePath(String path) => _send('POST', '/api/index/include', {'path': path, 'reindex': true});
  Future<void> pauseFolder(String path) => _send('POST', '/api/folders/pause', {'path': path});
  Future<void> resumeFolder(String path) => _send('POST', '/api/folders/resume', {'path': path, 'reindex': true});
  Future<int> clearFolder(String path, {bool reindex = false}) async =>
      (await _send('POST', '/api/folders/clear', {'path': path, 'reindex': reindex}))['removed'] ?? 0;
  Future<Map<String, dynamic>> indexProgress() async => await _get('/api/index');

  Future<Map<String, dynamic>> providers() async => await _get('/api/providers');
  Future<Map<String, dynamic>> saveProvider(Map<String, dynamic> p) async => await _send('POST', '/api/providers', p);
  Future<void> deleteProvider(String id) => _send('DELETE', '/api/providers/$id');
  Future<List<dynamic>> providerModels(String id) async => await _get('/api/providers/$id/models');
  Future<Map<String, dynamic>> testProvider(String id) async => await _send('POST', '/api/providers/$id/test');
  Future<Map<String, dynamic>> pullModel(String model) async => await _send('POST', '/api/providers/ollama/pull', {'model': model});
  /// Try a model on a job before using it; a local model may need a minute to load.
  Future<Map<String, dynamic>> checkModel(String role, String provider, String model) async =>
      await _send('POST', '/api/models/check', {'role': role, 'provider': provider, 'model': model}, const Duration(minutes: 3));
  Future<Map<String, dynamic>> setRole(String role, String provider, String model) async =>
      await _send('PUT', '/api/roles', {'role': role, 'provider': provider, 'model': model});

  Future<Map<String, dynamic>> pairStart() async => await _send('POST', '/api/pair/start');
  Future<Map<String, dynamic>> pair(String code, String name) async =>
      await _send('POST', '/api/pair', {'code': code, 'name': name});
  Future<List<dynamic>> devices() async => await _get('/api/devices');
  Future<void> unpair(String id) => _send('DELETE', '/api/devices/$id');
}
