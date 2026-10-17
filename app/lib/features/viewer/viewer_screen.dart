import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/app_state.dart';
import '../../core/errors/errors.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/marked_text.dart';
import 'document_view.dart';
import 'finder.dart';
import 'image_view.dart';
import 'media_view.dart';
import 'pdf_view.dart';
import 'text_view.dart';

/// A file to show, and what the search found in it (words to mark, a moment in a video).
class ViewTarget {
  ViewTarget(this.path, this.name, {this.terms = const [], this.at});
  ViewTarget.fromHit(Hit h) : this(h.path, h.name, terms: snippetTerms(h.snippet), at: h.at);
  final String path, name;
  final List<String> terms;
  final double? at;
}

/// What the viewer can ask the rest of the app to do.
class ViewerActions {
  const ViewerActions({required this.close, required this.openOnLaptop, required this.showInFolder, this.ask});
  final VoidCallback close;
  final void Function(String path, double start) openOnLaptop;
  final void Function(String path) showInFolder;
  final void Function(String name)? ask; // "Ask about it" (sends a chat message)
}

/// Reading a file in the app. [targets] are the results it came from: previous / next go through them.
class ViewerScreen extends StatefulWidget {
  const ViewerScreen({super.key, required this.api, required this.targets, this.index = 0, required this.actions, this.compact = false});
  final Api api;
  final List<ViewTarget> targets;
  final int index;
  final ViewerActions actions;
  final bool compact;

  @override
  State<ViewerScreen> createState() => _ViewerScreenState();
}

class _ViewerScreenState extends State<ViewerScreen> {
  late int index = widget.index;
  late Future<ViewInfo> info = _load();
  final finder = Finder();
  final _find = TextEditingController();

  ViewTarget get target => widget.targets[index];

  Future<ViewInfo> _load() => widget.api.viewInfo(target.path);

  void _go(int step) {
    final next = index + step;
    if (next < 0 || next >= widget.targets.length) return;
    setState(() {
      index = next;
      info = _load();
      _find.clear();
    });
  }

  @override
  void dispose() {
    finder.dispose();
    _find.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => CallbackShortcuts(
        bindings: {
          const SingleActivator(LogicalKeyboardKey.escape): widget.actions.close,
          const SingleActivator(LogicalKeyboardKey.arrowRight, alt: true): () => _go(1),
          const SingleActivator(LogicalKeyboardKey.arrowLeft, alt: true): () => _go(-1),
        },
        child: Focus(
          autofocus: true,
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            _bar(),
            Expanded(
              child: FutureBuilder<ViewInfo>(
                key: ValueKey(target.path),
                future: info,
                builder: (context, snap) {
                  if (snap.hasError) return _problem(userMessage(snap.error!));
                  if (!snap.hasData) return const Center(child: CircularProgressIndicator(color: C.accent));
                  return _body(snap.data!);
                },
              ),
            ),
          ]),
        ),
      );

  Widget _body(ViewInfo i) {
    final api = widget.api;
    return switch (i.kind) {
      'pdf' => PdfView(api: api, info: i, terms: target.terms, finder: finder),
      'image' => ImageView(api: api, info: i, onSwipe: _go),
      'text' || 'markdown' || 'code' => TextView(api: api, info: i, terms: target.terms, finder: finder),
      'document' || 'table' || 'slides' => DocumentView(api: api, info: i, terms: target.terms, finder: finder),
      'video' || 'audio' => MediaView(api: api, info: i, at: target.at, onPlayOnLaptop: (s) => widget.actions.openOnLaptop(i.path, s)),
      _ => _problem("This kind of file can't be shown in the app.", open: true),
    };
  }

  Widget _problem(String message, {bool open = false}) => Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.visibility_off_outlined, size: 32, color: C.muted),
          const SizedBox(height: 10),
          Text(message, textAlign: TextAlign.center, style: const TextStyle(color: C.text3)),
          if (open) ...[
            const SizedBox(height: 14),
            FilledButton(onPressed: () => widget.actions.openOnLaptop(target.path, 0), child: const Text('Open on the laptop')),
          ],
        ]),
      );

  Widget _bar() {
    final a = widget.actions;
    final many = widget.targets.length > 1;
    return Container(
      padding: EdgeInsets.fromLTRB(8, 6, widget.compact ? 4 : 12, 6),
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: C.line))),
      child: Row(children: [
        IconButton(tooltip: 'Back (Esc)', onPressed: a.close, icon: const Icon(Icons.arrow_back)),
        const SizedBox(width: 4),
        Expanded(
          child: Text(target.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
        ),
        if (many) ...[
          IconButton(tooltip: 'Previous result', onPressed: index > 0 ? () => _go(-1) : null, icon: const Icon(Icons.chevron_left)),
          Text('${index + 1}/${widget.targets.length}', style: const TextStyle(color: C.muted, fontSize: 13)),
          IconButton(
            tooltip: 'Next result',
            onPressed: index < widget.targets.length - 1 ? () => _go(1) : null,
            icon: const Icon(Icons.chevron_right),
          ),
        ],
        if (!widget.compact)
          SizedBox(
            width: 200,
            child: TextField(
              controller: _find,
              onSubmitted: (q) => finder.find(q.trim()),
              decoration: const InputDecoration(hintText: 'Find in file', isDense: true, prefixIcon: Icon(Icons.search, size: 18)),
            ),
          ),
        PopupMenuButton<String>(
          tooltip: 'More',
          onSelected: (v) => switch (v) {
            'open' => a.openOnLaptop(target.path, target.at ?? 0),
            'show' => a.showInFolder(target.path),
            'ask' => a.ask?.call(target.name),
            'find' => unawaited(_askFind()),
            _ => null,
          },
          itemBuilder: (_) => [
            if (widget.compact) const PopupMenuItem(value: 'find', child: Text('Find in file')),
            PopupMenuItem(value: 'open', child: Text(widget.compact ? 'Open on the laptop' : 'Open in default app')),
            const PopupMenuItem(value: 'show', child: Text('Show in folder')),
            if (a.ask != null) const PopupMenuItem(value: 'ask', child: Text('Ask about it')),
          ],
        ),
      ]),
    );
  }

  Future<void> _askFind() async {
    final q = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Find in file'),
        content: TextField(controller: _find, autofocus: true, onSubmitted: (v) => Navigator.pop(context, v)),
        actions: [FilledButton(onPressed: () => Navigator.pop(context, _find.text), child: const Text('Find'))],
      ),
    );
    if (q != null) finder.find(q.trim());
  }
}
