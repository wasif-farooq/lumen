/// How numbers, dates, times and paths are written in the app.
library;

/// 1536 -> "1.5 KB"
String humanSize(int n) {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  double v = n.toDouble();
  var i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return i == 0 ? '$n B' : '${v.toStringAsFixed(1)} ${units[i]}';
}

/// File time (seconds since 1970) -> "Jun 1, 2019"
String humanDate(double mtime) {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  final d = DateTime.fromMillisecondsSinceEpoch((mtime * 1000).round());
  return '${months[d.month - 1]} ${d.day}, ${d.year}';
}

/// Seconds -> "1:02:05" / "2:05"
String clock(double seconds) {
  final s = seconds.floor();
  final h = s ~/ 3600, m = s % 3600 ~/ 60, sec = s % 60;
  String two(int x) => x.toString().padLeft(2, '0');
  return h > 0 ? '$h:${two(m)}:${two(sec)}' : '$m:${two(sec)}';
}

/// /home/alex/Documents -> ~/Documents
String shortPath(String path) {
  const home = '/home/';
  if (path.startsWith(home)) {
    final rest = path.substring(home.length);
    final slash = rest.indexOf('/');
    if (slash > 0) return '~${rest.substring(slash)}';
  }
  return path;
}
