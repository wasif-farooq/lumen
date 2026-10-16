import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../core/format.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';

/// The preview picture: a thumbnail for PDFs, images and videos, a file badge otherwise.
class PreviewThumb extends StatelessWidget {
  const PreviewThumb({super.key, required this.api, required this.hit});
  final Api api;
  final Hit hit;

  @override
  Widget build(BuildContext context) {
    final previewable = const {'pdf', 'image', 'video'}.contains(hit.kind);
    return Container(
      height: 240,
      decoration: BoxDecoration(color: const Color(0xFF1B1F24), borderRadius: BorderRadius.circular(12), border: Border.all(color: C.line)),
      clipBehavior: Clip.antiAlias,
      alignment: Alignment.center,
      child: previewable
          ? Padding(
              padding: EdgeInsets.all(hit.kind == 'pdf' ? 14 : 0),
              child: ApiImage(api: api, path: hit.path, w: 640, t: hit.at, fit: hit.kind == 'pdf' ? BoxFit.contain : BoxFit.cover),
            )
          : FileBadge(kind: hit.kind, ext: hit.ext, width: 64, height: 76),
    );
  }
}

class SegmentRow extends StatelessWidget {
  const SegmentRow({super.key, required this.seg, required this.current, required this.onTap});
  final Segment seg;
  final bool current;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
        color: current ? const Color(0xFF2A2419) : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          borderRadius: BorderRadius.circular(8),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SizedBox(width: 52, child: Text(seg.time, style: monoStyle(color: current ? C.accent : C.muted))),
              Expanded(child: Text(seg.text, style: TextStyle(fontSize: 13, color: current ? C.text : C.text2))),
            ]),
          ),
        ),
      );
}

class FileMeta extends StatelessWidget {
  const FileMeta({super.key, required this.hit, required this.info});
  final Hit hit;
  final FileInfo? info;

  @override
  Widget build(BuildContext context) {
    final rows = <(String, String)>[
      ('Type', switch (hit.kind) { 'pdf' => 'PDF document', 'image' => 'Image', 'video' => 'Video', 'audio' => 'Audio', 'doc' => 'Document', 'sheet' => 'Spreadsheet', _ => hit.ext.toUpperCase() }),
      ('Size', humanSize(hit.size)),
      if (hit.duration != null) ('Length', clock(hit.duration!)) else ('Modified', humanDate(hit.mtime)),
      ('Search', info == null ? '…' : (info!.searchable ? 'Contents' : 'Name only')),
    ];
    return Wrap(runSpacing: 12, children: [
      for (final (k, v) in rows)
        FractionallySizedBox(
          widthFactor: 0.5,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(k, style: const TextStyle(fontSize: 13, color: C.muted)),
            Text(v, style: const TextStyle(fontSize: 13)),
          ]),
        ),
    ]);
  }
}
