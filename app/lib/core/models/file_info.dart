/// One line of a transcript, with where it starts.
class Segment {
  final double start;
  final String text, time;

  Segment.fromJson(Map<String, dynamic> j)
      : start = (j['start'] as num).toDouble(),
        text = j['text'] as String? ?? '',
        time = j['time'] as String? ?? '';
}

/// Details of one file for the preview panel.
class FileInfo {
  final Map<String, dynamic> j;
  FileInfo(this.j);

  String get path => j['path'] as String;
  String get name => j['name'] as String;
  String get kind => j['kind'] as String;
  String get folder => j['folder'] as String;
  String get caption => j['caption'] as String? ?? '';
  String get excerpt => j['excerpt'] as String? ?? '';
  int get size => (j['size'] as num? ?? 0).toInt();
  double get mtime => (j['mtime'] as num? ?? 0).toDouble();
  double? get duration => (j['duration'] as num?)?.toDouble();
  bool get searchable => j['searchable'] == true;
  List<Segment> get segments =>
      [for (final s in j['segments'] as List? ?? const []) Segment.fromJson(Map<String, dynamic>.from(s as Map))];
}
