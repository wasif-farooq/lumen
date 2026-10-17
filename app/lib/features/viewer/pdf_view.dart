import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import 'finder.dart';

/// A PDF: its pages (drawn by the server at the size shown), opening at the page the search matched,
/// matches outlined, zoom, and "find in file".
class PdfView extends StatefulWidget {
  const PdfView({super.key, required this.api, required this.info, this.terms = const [], required this.finder});
  final Api api;
  final ViewInfo info;
  final List<String> terms; // the search's words: open where they are
  final Finder finder;

  @override
  State<PdfView> createState() => _PdfViewState();
}

class _PdfViewState extends State<PdfView> {
  final _scroll = ScrollController();
  double zoom = 1;
  List<PdfMatch> matches = [];
  int match = 0; // which match is shown
  int page = 0; // the page in view
  double _pageWidth = 800;

  ViewInfo get info => widget.info;

  @override
  void initState() {
    super.initState();
    widget.finder.addListener(_onFind);
    _scroll.addListener(_onScroll);
    if (widget.terms.isNotEmpty) unawaited(_find(widget.terms.join(' ')));
  }

  @override
  void dispose() {
    widget.finder.removeListener(_onFind);
    _scroll.dispose();
    super.dispose();
  }

  void _onFind() {
    if (widget.finder.times > 0 && matches.isNotEmpty) return _step(1); // the same words again: next match
    unawaited(_find(widget.finder.query));
  }

  Future<void> _find(String q) async {
    if (q.isEmpty) {
      setState(() => matches = []);
      return;
    }
    final found = await widget.api.pdfFind(info.path, q);
    if (!mounted) return;
    setState(() {
      matches = found;
      match = 0;
    });
    if (found.isNotEmpty) _jump(found.first.page, topFraction: found.first.rects.firstOrNull?[1] ?? 0);
  }

  double _shape(int i) => i < info.shapes.length ? info.shapes[i] : (info.shapes.lastOrNull ?? 1.414);
  double _height(int i) => _pageWidth * _shape(i) + 12;

  void _jump(int target, {double topFraction = 0}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      var y = 0.0;
      for (var i = 0; i < target; i++) {
        y += _height(i);
      }
      y += math.max(0, topFraction * _pageWidth * _shape(target) - 80); // the match a little below the top
      _scroll.jumpTo(y.clamp(0, _scroll.position.maxScrollExtent));
    });
  }

  void _onScroll() {
    var y = 0.0, i = 0;
    while (i < info.pages - 1 && y + _height(i) <= _scroll.offset + 1) {
      y += _height(i++);
    }
    if (i != page) setState(() => page = i);
  }

  void _step(int by) {
    if (matches.isEmpty) return;
    setState(() => match = (match + by) % matches.length);
    final m = matches[match];
    _jump(m.page, topFraction: m.rects.firstOrNull?[1] ?? 0);
  }

  /// The server draws pages at a few sizes (shared cache), the next one up from what's needed.
  int _drawWidth(double logical) {
    final px = logical * MediaQuery.devicePixelRatioOf(context);
    return const [600, 900, 1200, 1600, 2400].firstWhere((w) => w >= px, orElse: () => 2400);
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, box) {
        _pageWidth = math.max(200, (box.maxWidth - 32) * zoom);
        final list = ListView.builder(
          controller: _scroll,
          itemCount: info.pages,
          itemExtentBuilder: (i, _) => _height(i),
          itemBuilder: (context, i) => _page(i),
        );
        return Stack(children: [
          Positioned.fill(
            child: zoom <= 1
                ? Center(child: SizedBox(width: _pageWidth, child: list))
                : SingleChildScrollView(scrollDirection: Axis.horizontal, child: SizedBox(width: _pageWidth + 32, child: list)),
          ),
          Positioned(right: 12, bottom: 12, child: _controls()),
        ]);
      });

  Widget _page(int i) {
    final marks = matches.where((m) => m.page == i).expand((m) => m.rects).toList();
    final current = matches.isNotEmpty && matches[match].page == i;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Container(
        color: Colors.white,
        child: Stack(fit: StackFit.expand, children: [
          Image.network(
            widget.api.pageUrl(info.path, i, w: _drawWidth(_pageWidth)),
            headers: widget.api.headers,
            fit: BoxFit.fill,
            gaplessPlayback: true,
            errorBuilder: (_, _, _) => const Center(child: Icon(Icons.broken_image_outlined, color: C.muted)),
          ),
          for (final r in marks)
            Positioned(
              left: r[0] * _pageWidth,
              top: r[1] * _pageWidth * _shape(i),
              width: (r[2] - r[0]) * _pageWidth,
              height: (r[3] - r[1]) * _pageWidth * _shape(i),
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0x55F0A53A),
                  border: Border.all(color: current ? C.accent : const Color(0x88F0A53A), width: current ? 2 : 1),
                ),
              ),
            ),
        ]),
      ),
    );
  }

  Widget _controls() => Material(
        color: C.raised,
        elevation: 4,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 6),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Text('Page ${page + 1} of ${info.pages}', style: const TextStyle(fontSize: 13, color: C.text2)),
            if (matches.isNotEmpty) ...[
              const SizedBox(width: 8),
              IconButton(tooltip: 'Previous match', onPressed: () => _step(-1), icon: const Icon(Icons.keyboard_arrow_up, size: 20)),
              Text('${match + 1}/${matches.length} pages', style: const TextStyle(fontSize: 12.5, color: C.accent)),
              IconButton(tooltip: 'Next match', onPressed: () => _step(1), icon: const Icon(Icons.keyboard_arrow_down, size: 20)),
            ],
            IconButton(tooltip: 'Zoom out', onPressed: zoom > 0.5 ? () => setState(() => zoom -= 0.25) : null, icon: const Icon(Icons.remove, size: 18)),
            Text('${(zoom * 100).round()}%', style: const TextStyle(fontSize: 12.5, color: C.text3)),
            IconButton(tooltip: 'Zoom in', onPressed: zoom < 3 ? () => setState(() => zoom += 0.25) : null, icon: const Icon(Icons.add, size: 18)),
          ]),
        ),
      );
}
