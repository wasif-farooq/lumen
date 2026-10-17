import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../core/errors/errors.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/marked_text.dart';
import 'finder.dart';

/// Word, Excel, PowerPoint, OpenDocument and EPUB files (and CSV) as a readable document: headings,
/// paragraphs, real tables, and slide / sheet / chapter dividers; the search's words marked.
class DocumentView extends StatefulWidget {
  const DocumentView({super.key, required this.api, required this.info, this.terms = const [], required this.finder});
  final Api api;
  final ViewInfo info;
  final List<String> terms;
  final Finder finder;

  @override
  State<DocumentView> createState() => _DocumentViewState();
}

class _DocumentViewState extends State<DocumentView> {
  final _scroll = ScrollController();
  List<DocBlock>? blocks;
  bool cut = false;
  Object? error;
  late List<String> terms = widget.terms;
  final _keys = <int, GlobalKey>{};
  int? hit;

  @override
  void initState() {
    super.initState();
    widget.finder.addListener(_onFind);
    unawaited(_load());
  }

  @override
  void dispose() {
    widget.finder.removeListener(_onFind);
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final (b, c) = await widget.api.docBlocks(widget.info.path);
      if (!mounted) return;
      setState(() {
        blocks = b;
        cut = c;
      });
      if (terms.isNotEmpty) _findFrom(0);
    } on Object catch (e) {
      if (mounted) setState(() => error = e);
    }
  }

  void _onFind() {
    final q = widget.finder.query;
    setState(() => terms = q.isEmpty ? widget.terms : [q]);
    if (q.isNotEmpty) _findFrom(widget.finder.times > 0 && hit != null ? hit! + 1 : 0);
  }

  void _findFrom(int start) {
    final b = blocks ?? const [];
    final re = RegExp(terms.map(RegExp.escape).join('|'), caseSensitive: false);
    for (var i = start; i < b.length; i++) {
      if (re.hasMatch(b[i].text) || b[i].rows.any((r) => r.any(re.hasMatch))) {
        setState(() => hit = i);
        WidgetsBinding.instance.addPostFrameCallback((_) => _show(i));
        return;
      }
    }
  }

  /// Scroll to block [i]: roughly (it may not be built yet), then exactly.
  void _show(int i) {
    final ctx = _keys[i]?.currentContext;
    if (ctx != null) {
      Scrollable.ensureVisible(ctx, alignment: 0.15, duration: const Duration(milliseconds: 200));
    } else if (_scroll.hasClients) {
      final b = blocks!;
      _scroll.jumpTo((_scroll.position.maxScrollExtent * i / b.length).clamp(0, _scroll.position.maxScrollExtent));
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final again = _keys[i]?.currentContext;
        if (again != null) Scrollable.ensureVisible(again, alignment: 0.15);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (error != null) return Center(child: Text(userMessage(error!), style: const TextStyle(color: C.text3)));
    final b = blocks;
    if (b == null) return const Center(child: CircularProgressIndicator(color: C.accent));
    if (b.isEmpty) return const Center(child: Text('No text in this file.', style: TextStyle(color: C.text3)));
    return SelectionArea(
      child: ListView.builder(
        controller: _scroll,
        padding: const EdgeInsets.fromLTRB(28, 20, 28, 48),
        itemCount: b.length + (cut ? 1 : 0),
        itemBuilder: (context, i) {
          if (i == b.length) {
            return const Padding(
              padding: EdgeInsets.only(top: 12),
              child: Text('The document is longer: open it in its own app to see the rest.', style: TextStyle(color: C.muted)),
            );
          }
          return Center(
            key: _keys.putIfAbsent(i, GlobalKey.new),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 900),
              child: Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Align(alignment: Alignment.centerLeft, child: _block(b[i], i == hit)),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _block(DocBlock b, bool current) {
    switch (b.type) {
      case 'heading':
        final size = const [22.0, 18.5, 16.0][(b.level - 1).clamp(0, 2)];
        return Text.rich(TextSpan(children: markTerms(b.text, terms)), style: TextStyle(fontSize: size, fontWeight: FontWeight.w600));
      case 'break':
        return Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Row(children: [
            Text(b.text, style: const TextStyle(color: C.accent, fontWeight: FontWeight.w600, fontSize: 13)),
            const SizedBox(width: 10),
            const Expanded(child: Divider(color: C.line2)),
          ]),
        );
      case 'table':
        return _Table(rows: b.rows, terms: terms);
      default:
        return Container(
          color: current ? const Color(0x22F0A53A) : null,
          child: Text.rich(
            TextSpan(children: markTerms(b.text, terms)),
            style: TextStyle(fontSize: 14.5, height: 1.55, color: b.style == 'notes' ? C.text3 : C.text,
                fontStyle: b.style == 'notes' ? FontStyle.italic : null),
          ),
        );
    }
  }
}

/// A table that scrolls sideways when it is wider than the page; the first row as its header.
class _Table extends StatelessWidget {
  const _Table({required this.rows, required this.terms});
  final List<List<String>> rows;
  final List<String> terms;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Table(
          defaultColumnWidth: const IntrinsicColumnWidth(),
          border: TableBorder.all(color: C.line2),
          children: [
            for (final (i, row) in rows.indexed)
              TableRow(
                decoration: BoxDecoration(color: i == 0 ? C.surface2 : (i.isEven ? C.surface : null)),
                children: [
                  for (final cell in row)
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 360),
                        child: Text.rich(
                          TextSpan(children: markTerms(cell, terms)),
                          style: TextStyle(fontSize: 13.5, fontWeight: i == 0 ? FontWeight.w600 : null),
                        ),
                      ),
                    ),
                ],
              ),
          ],
        ),
      );
}
