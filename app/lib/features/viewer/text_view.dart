import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/markdown.dart';
import '../../shared/widgets/marked_text.dart';
import 'finder.dart';

const _lineHeight = 20.0; // code and logs: one line each, no wrapping
const _searchAhead = 8 * 1024 * 1024; // bytes loaded at most to find a match further down
const _markdownMax = 2 * 1024 * 1024; // Markdown is shown whole up to this size

/// Text, code and Markdown: loads as you scroll (a huge log opens at once), code with line numbers,
/// Markdown formatted, the search's words marked, opening at the first one; "find in file".
class TextView extends StatefulWidget {
  const TextView({super.key, required this.api, required this.info, this.terms = const [], required this.finder});
  final Api api;
  final ViewInfo info;
  final List<String> terms;
  final Finder finder;

  @override
  State<TextView> createState() => _TextViewState();
}

class _TextViewState extends State<TextView> {
  final _scroll = ScrollController();
  final lines = <String>[];
  String _partial = ''; // the last line of a piece, continued in the next
  int _next = 0;
  bool done = false, loading = false;
  Object? error;
  late List<String> terms = widget.terms;
  int? hit; // the line with the match being shown

  ViewInfo get info => widget.info;
  bool get wraps => info.kind != 'code';

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    widget.finder.addListener(_onFind);
    unawaited(_start());
  }

  @override
  void dispose() {
    widget.finder.removeListener(_onFind);
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _start() async {
    await _more();
    if (info.kind == 'markdown') {
      while (!done && _next < _markdownMax && mounted) {
        await _more();
      }
    }
    if (terms.isNotEmpty) await _findFrom(0);
  }

  Future<void> _more() async {
    if (done || loading) return;
    loading = true;
    try {
      final piece = await widget.api.textPiece(info.path, offset: _next);
      final parts = (_partial + piece.text).split('\n');
      _partial = piece.done ? '' : parts.removeLast();
      lines.addAll(parts);
      if (piece.done && _partial.isNotEmpty) lines.add(_partial);
      _next = piece.next;
      done = piece.done;
    } on Object catch (e) {
      error = e;
      done = true;
    }
    loading = false;
    if (mounted) setState(() {});
  }

  void _onScroll() {
    if (_scroll.position.extentAfter < 2000) unawaited(_more());
  }

  void _onFind() {
    final q = widget.finder.query;
    setState(() => terms = q.isEmpty ? widget.terms : [q]);
    if (q.isNotEmpty) unawaited(_findFrom(widget.finder.times > 0 && hit != null ? hit! + 1 : 0));
  }

  /// The first line from [start] with one of the words, loading further pieces if needed.
  Future<void> _findFrom(int start) async {
    final re = RegExp(terms.map(RegExp.escape).join('|'), caseSensitive: false);
    var i = start;
    while (mounted) {
      for (; i < lines.length; i++) {
        if (re.hasMatch(lines[i])) {
          setState(() => hit = i);
          return _jump(i);
        }
      }
      if (done || _next > _searchAhead) return;
      await _more();
    }
  }

  void _jump(int line) {
    if (info.kind == 'markdown') return; // shown whole: the marks show where
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      final perLine = wraps && lines.isNotEmpty
          ? (_scroll.position.maxScrollExtent + _scroll.position.viewportDimension) / lines.length
          : _lineHeight;
      _scroll.jumpTo((line * perLine - 80).clamp(0, _scroll.position.maxScrollExtent));
    });
  }

  @override
  Widget build(BuildContext context) {
    if (error != null && lines.isEmpty) {
      return Center(child: Text('$error', style: const TextStyle(color: C.text3)));
    }
    if (lines.isEmpty) return const Center(child: CircularProgressIndicator(color: C.accent));
    if (info.kind == 'markdown') {
      return SingleChildScrollView(
        controller: _scroll,
        padding: const EdgeInsets.fromLTRB(28, 20, 28, 40),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 820),
            child: MarkdownView(lines.join('\n'), terms: terms),
          ),
        ),
      );
    }
    final digits = '${lines.length}'.length;
    final list = ListView.builder(
      controller: _scroll,
      padding: const EdgeInsets.fromLTRB(12, 12, 24, 40),
      itemCount: lines.length + (done ? 0 : 1),
      itemExtent: wraps ? null : _lineHeight,
      itemBuilder: (context, i) {
        if (i == lines.length) return const Padding(padding: EdgeInsets.all(8), child: LinearProgressIndicator(color: C.accent));
        final style = wraps ? const TextStyle(fontSize: 14.5, height: 1.5) : monoStyle(size: 13, color: C.text);
        return Container(
          color: i == hit ? const Color(0x22F0A53A) : null,
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (!wraps)
              SizedBox(
                width: digits * 9.0 + 16,
                child: Text('${i + 1}', textAlign: TextAlign.right, style: monoStyle(size: 12, color: C.muted)),
              ),
            if (!wraps) const SizedBox(width: 14),
            wraps
                ? Expanded(child: Text.rich(TextSpan(children: markTerms(lines[i], terms)), style: style))
                : Text.rich(TextSpan(children: markTerms(lines[i], terms)), style: style, softWrap: false),
          ]),
        );
      },
    );
    if (wraps) return SelectionArea(child: list);
    return SelectionArea(
      child: LayoutBuilder(
        builder: (context, box) => SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: SizedBox(width: box.maxWidth * 2.5, child: list), // long lines scroll sideways
        ),
      ),
    );
  }
}
