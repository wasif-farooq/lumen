import '../models/json.dart';
import '../models/view.dart';
import 'api_client.dart';

/// Reading files in the app: what a file is, PDF pages and matches, full-size images, text in
/// pieces, documents as blocks, and media streams.
mixin ViewerApi on ApiClient {
  Future<ViewInfo> viewInfo(String path) async => ViewInfo.fromJson(mapOf(await getJson('/api/view', {'path': path})));

  String pageUrl(String path, int page, {int w = 1200}) =>
      uri('/api/view/page', {'path': path, 'page': '$page', 'w': '$w'}).toString();

  String imageUrl(String path, {int w = 2000}) => uri('/api/view/image', {'path': path, 'w': '$w'}).toString();

  String streamUrl(String path) => uri('/api/view/stream', {'path': path}).toString();

  Future<List<PdfMatch>> pdfFind(String path, String query) async =>
      [for (final m in listOf(await getJson('/api/view/find', {'path': path, 'q': query}))) PdfMatch.fromJson(m)];

  Future<String> pageText(String path, int page) async =>
      mapOf(await getJson('/api/view/page-text', {'path': path, 'page': '$page'}))['text'] as String? ?? '';

  Future<TextPiece> textPiece(String path, {int offset = 0, int limit = 256 * 1024}) async =>
      TextPiece.fromJson(mapOf(await getJson('/api/view/text', {'path': path, 'offset': '$offset', 'limit': '$limit'})));

  /// The document's blocks, and whether it was longer than shown.
  Future<(List<DocBlock>, bool)> docBlocks(String path) async {
    final j = mapOf(await getJson('/api/view/blocks', {'path': path}));
    return ([for (final b in listOf(j['blocks'])) DocBlock.fromJson(b)], j['cut'] == true);
  }
}
