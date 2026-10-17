/// What the viewer gets from the server: what a file is, PDF matches, text pieces, document blocks.
library;

class ViewInfo {
  final String path, name, ext;
  final String kind; // pdf | image | markdown | text | code | document | table | slides | video | audio | other
  final int size;
  final int pages; // PDF
  final List<double> shapes; // PDF: each page's height / width
  final String language; // code
  final double? duration; // video, audio

  ViewInfo.fromJson(Map<String, dynamic> j)
      : path = j['path'] as String? ?? '',
        name = j['name'] as String? ?? '',
        ext = j['ext'] as String? ?? '',
        kind = j['kind'] as String? ?? 'other',
        size = (j['size'] as num? ?? 0).toInt(),
        pages = (j['pages'] as num? ?? 0).toInt(),
        shapes = [for (final s in j['shapes'] as List? ?? const []) (s as num).toDouble()],
        language = j['language'] as String? ?? '',
        duration = (j['duration'] as num?)?.toDouble();

  bool get isText => kind == 'text' || kind == 'markdown' || kind == 'code';
  bool get isDocument => kind == 'document' || kind == 'table' || kind == 'slides';
  bool get isMedia => kind == 'video' || kind == 'audio';
}

/// Where words are on a PDF page: rectangles as fractions of the page (left, top, right, bottom).
class PdfMatch {
  final int page;
  final List<List<double>> rects;

  PdfMatch.fromJson(Map<String, dynamic> j)
      : page = (j['page'] as num).toInt(),
        rects = [for (final r in j['rects'] as List? ?? const []) [for (final v in r as List) (v as num).toDouble()]];
}

class TextPiece {
  final int offset, next, size;
  final bool done;
  final String text;

  TextPiece.fromJson(Map<String, dynamic> j)
      : offset = (j['offset'] as num? ?? 0).toInt(),
        next = (j['next'] as num? ?? 0).toInt(),
        size = (j['size'] as num? ?? 0).toInt(),
        done = j['done'] == true,
        text = j['text'] as String? ?? '';
}

/// A heading, paragraph, table, or slide / sheet / chapter break.
class DocBlock {
  final String type; // heading | paragraph | table | break
  final String text; // heading, paragraph; the label of a break
  final int level; // heading
  final String style; // "notes" for a slide's speaker notes
  final List<List<String>> rows; // table

  DocBlock.fromJson(Map<String, dynamic> j)
      : type = j['type'] as String? ?? 'paragraph',
        text = (j['text'] ?? j['label'] ?? '') as String,
        level = (j['level'] as num? ?? 1).toInt(),
        style = j['style'] as String? ?? '',
        rows = [for (final r in j['rows'] as List? ?? const []) [for (final c in r as List) '$c']];
}
