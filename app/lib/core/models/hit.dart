/// One file found by a search or by the agent.
class Hit {
  final String path, name, ext, kind, snippet, atText;
  final int size;
  final double mtime;
  final double? duration, at;

  Hit.fromJson(Map<String, dynamic> j)
      : path = j['path'] as String? ?? '',
        name = j['name'] as String? ?? '',
        ext = j['ext'] as String? ?? '',
        kind = j['kind'] as String? ?? 'file',
        snippet = j['snippet'] as String? ?? '',
        atText = j['at_text'] as String? ?? '',
        size = (j['size'] as num? ?? 0).toInt(),
        mtime = (j['mtime'] as num? ?? 0).toDouble(),
        duration = (j['duration'] as num?)?.toDouble(),
        at = (j['at'] as num?)?.toDouble();

  static List<Hit> listFrom(Object? json) =>
      [for (final h in json as List? ?? const []) Hit.fromJson(Map<String, dynamic>.from(h as Map))];

  String get folder => path.substring(0, path.lastIndexOf('/').clamp(0, path.length));
  bool get isMedia => kind == 'video' || kind == 'audio';
}
