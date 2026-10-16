import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';
import '../chat/results.dart';
import '../chat/video_card.dart';
import 'file_details_parts.dart';
import '../../core/format.dart';
import '../../core/errors/run_guarded.dart';

/// Right-hand panel (desktop) / sheet body (mobile): preview, details, transcript, actions.
class FileDetails extends StatefulWidget {
  const FileDetails({super.key, required this.api, required this.hit, required this.onOpen, required this.onShow, required this.onAsk, this.onClose, this.onSimilar, this.mobile = false});
  final Api api;
  final Hit hit;
  final HitAction onOpen;
  final VoidCallback onShow;
  final void Function(String question) onAsk;
  final VoidCallback? onClose;
  final VoidCallback? onSimilar; // images: find ones that look like this
  final bool mobile;

  @override
  State<FileDetails> createState() => _FileDetailsState();
}

class _FileDetailsState extends State<FileDetails> {
  Future<FileInfo>? _info;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(FileDetails old) {
    super.didUpdateWidget(old);
    if (old.hit.path != widget.hit.path || old.hit.at != widget.hit.at) _load();
  }

  void _load() => _info = widget.api.file(widget.hit.path, at: widget.hit.at);

  Future<void> _removeFromIndex(Hit hit) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('Remove ${hit.name} from the index?'),
        content: const Text(
          'It will no longer show up in search, and later runs skip it. The file itself is not touched. '
          'You can include it again under Sync.',
          style: TextStyle(color: C.text3),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Remove from index')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    final removed = await runGuarded(context, () => widget.api.excludePath(hit.path),
        failure: 'Could not remove ${hit.name}', success: (_) => '${hit.name} removed from the index');
    if (removed != null) widget.onClose?.call();
  }

  @override
  Widget build(BuildContext context) {
    final hit = widget.hit;
    final media = hit.isMedia;
    final at = hit.at;
    return FutureBuilder<FileInfo>(
      future: _info,
      builder: (context, snap) {
        final info = snap.data;
        return ListView(
          padding: EdgeInsets.fromLTRB(20, widget.mobile ? 0 : 16, 20, 24),
          shrinkWrap: widget.mobile,
          children: [
            if (!widget.mobile)
              Row(children: [
                Expanded(child: Text(media ? 'TRANSCRIPT' : 'PREVIEW', style: const TextStyle(fontSize: 12.5, color: C.muted, letterSpacing: 0.8, fontWeight: FontWeight.w500))),
                if (widget.onClose != null) IconButton(tooltip: 'Close preview', onPressed: widget.onClose, icon: const Icon(Icons.close, size: 18, color: C.muted)),
              ]),
            if (!media || widget.mobile) ...[
              const SizedBox(height: 8),
              PreviewThumb(api: widget.api, hit: hit),
              const SizedBox(height: 16),
            ],
            Text(hit.name, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            SelectableText(shortPath(hit.path), style: monoStyle()),
            if (media && at != null && widget.mobile) ...[
              const SizedBox(height: 14),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(color: const Color(0xFF1F242A), borderRadius: BorderRadius.circular(12)),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(clock(at), style: monoStyle(size: 13, color: C.accent)),
                  const SizedBox(width: 12),
                  Expanded(child: Text('“${hit.atText}”')),
                ]),
              ),
              const SizedBox(height: 12),
              Timeline(position: (hit.duration ?? 0) > 0 ? at / hit.duration! : 0),
            ],
            const SizedBox(height: 16),
            if (media && info != null && info.segments.isNotEmpty && !widget.mobile) ...[
              for (final seg in info.segments.take(14))
                SegmentRow(seg: seg, current: at != null && (seg.start - at).abs() < 0.5, onTap: () => widget.onOpen(hit, start: seg.start)),
              const Divider(height: 28),
            ],
            FileMeta(hit: hit, info: info),
            if (info != null && info.caption.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text(media ? 'What it shows' : 'What the picture shows', style: const TextStyle(fontSize: 13, color: C.muted)),
              const SizedBox(height: 6),
              Text(info.caption, style: const TextStyle(fontSize: 13, color: Color(0xFFC3CAD1), height: 1.6)),
            ] else if (info != null && !media && hit.snippet.isNotEmpty) ...[
              const SizedBox(height: 16),
              const Text('Matched text', style: TextStyle(fontSize: 13, color: C.muted)),
              const SizedBox(height: 6),
              Highlighted(hit.snippet, style: const TextStyle(fontSize: 13, color: Color(0xFFC3CAD1), height: 1.6)),
            ],
            const SizedBox(height: 20),
            FilledButton.icon(
              onPressed: () => widget.onOpen(hit, start: at ?? 0),
              icon: Icon(media ? Icons.play_arrow_rounded : Icons.open_in_new, size: 18),
              label: Text(media
                  ? (at != null ? 'Play${widget.mobile ? ' on laptop' : ''} at ${clock(at)}' : 'Play${widget.mobile ? ' on laptop' : ''}')
                  : (widget.mobile ? 'Open on laptop' : 'Open')),
            ),
            if (hit.kind == 'image' && widget.onSimilar != null) ...[
              const SizedBox(height: 8),
              OutlinedButton.icon(onPressed: widget.onSimilar, icon: const Icon(Icons.image_search, size: 18), label: const Text('Find similar images')),
            ],
            const SizedBox(height: 8),
            Row(children: [
              Expanded(child: OutlinedButton(onPressed: widget.onShow, child: const Text('Show in folder'))),
              const SizedBox(width: 8),
              Expanded(child: OutlinedButton(onPressed: () => widget.onAsk('What is in ${hit.name}?'), child: const Text('Ask about it'))),
            ]),
            if (!widget.mobile) ...[
              const SizedBox(height: 8),
              TextButton.icon(
                onPressed: () {
                  unawaited(Clipboard.setData(ClipboardData(text: hit.path)));
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Path copied')));
                },
                icon: const Icon(Icons.copy, size: 14),
                label: const Text('Copy path'),
              ),
              TextButton.icon(
                onPressed: () => _removeFromIndex(hit),
                style: TextButton.styleFrom(foregroundColor: C.muted),
                icon: const Icon(Icons.block, size: 14),
                label: const Text('Remove from index'),
              ),
            ],
          ],
        );
      },
    );
  }
}
