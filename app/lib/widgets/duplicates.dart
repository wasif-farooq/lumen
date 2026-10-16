import 'package:flutter/material.dart';

import '../api.dart';
import '../theme.dart';
import 'common.dart';

/// One group of duplicate images: thumbnails side by side, the copy to keep marked.
class DuplicateGroupCard extends StatelessWidget {
  const DuplicateGroupCard({super.key, required this.group, required this.api, required this.onOpen, required this.onShow, this.compact = false});
  final DupGroup group;
  final Api api;
  final void Function(Hit) onOpen, onShow;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final tile = compact ? 120.0 : 168.0;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: C.surface, borderRadius: BorderRadius.circular(12), border: Border.all(color: C.line)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: group.identical ? const Color(0xFF1C3127) : const Color(0xFF2C2440),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(group.identical ? 'Identical files' : 'Same picture',
                style: TextStyle(fontSize: 12, color: group.identical ? const Color(0xFF8FDCB0) : const Color(0xFFC3A8FF))),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text('${group.files.length} copies · ${humanSize(group.reclaimable)} in extra copies',
                style: const TextStyle(fontSize: 13, color: C.text3)),
          ),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 10, runSpacing: 10, children: [
          for (final f in group.files)
            SizedBox(
              width: tile,
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Material(
                  color: C.surface2,
                  borderRadius: BorderRadius.circular(8),
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: () => onOpen(f),
                    child: Stack(children: [
                      SizedBox(width: tile, height: tile * 0.7, child: ApiImage(api: api, path: f.path, w: 320)),
                      if (f.path == group.keep)
                        Positioned(
                          left: 6,
                          top: 6,
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(color: C.accent, borderRadius: BorderRadius.circular(4)),
                            child: Text(group.identical ? 'Oldest' : 'Best quality',
                                style: const TextStyle(fontSize: 11, color: C.onAccent, fontWeight: FontWeight.w600)),
                          ),
                        ),
                    ]),
                  ),
                ),
                const SizedBox(height: 6),
                Text(f.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500)),
                Text(shortPath(f.folder), maxLines: 1, overflow: TextOverflow.ellipsis, style: monoStyle(size: 11)),
                Row(children: [
                  Expanded(child: Text('${humanSize(f.size)} · ${humanDate(f.mtime)}', style: const TextStyle(fontSize: 12, color: C.muted))),
                  IconButton(
                    tooltip: 'Show in folder',
                    visualDensity: VisualDensity.compact,
                    iconSize: 16,
                    onPressed: () => onShow(f),
                    icon: const Icon(Icons.folder_open_outlined, color: C.text3),
                  ),
                ]),
              ]),
            ),
        ]),
      ]),
    );
  }
}

/// Duplicates page: every group, biggest savings first. Never deletes anything.
class DuplicatesView extends StatefulWidget {
  const DuplicatesView({super.key, required this.api, required this.onOpen, required this.onShow, this.compact = false, this.embedded = false});
  final Api api;
  final void Function(Hit) onOpen, onShow;
  final bool compact;
  final bool embedded; // inside the Settings tabs: no page title

  @override
  State<DuplicatesView> createState() => _DuplicatesViewState();
}

class _DuplicatesViewState extends State<DuplicatesView> {
  late Future<List<DupGroup>> _groups = widget.api.duplicates();

  @override
  Widget build(BuildContext context) => FutureBuilder<List<DupGroup>>(
        future: _groups,
        builder: (context, snap) {
          final groups = snap.data ?? [];
          final total = groups.fold<int>(0, (a, g) => a + g.reclaimable);
          final pad = widget.compact ? 16.0 : 32.0;
          return ListView(padding: EdgeInsets.fromLTRB(pad, widget.compact ? 16 : (widget.embedded ? 20 : 28), pad, 40), children: [
            Row(children: [
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  if (!widget.compact && !widget.embedded) const Text('Duplicate images', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
                  Text(
                    snap.connectionState != ConnectionState.done
                        ? 'Comparing your images…'
                        : snap.hasError
                            ? 'Could not load: ${snap.error}'
                            : groups.isEmpty
                                ? 'No duplicates found.'
                                : '${groups.length} groups · ${humanSize(total)} could be freed by removing the extra copies',
                    style: const TextStyle(color: C.text3),
                  ),
                ]),
              ),
              IconButton(tooltip: 'Check again', onPressed: () => setState(() => _groups = widget.api.duplicates()), icon: const Icon(Icons.refresh)),
            ]),
            const SizedBox(height: 6),
            const Text('Nothing is deleted here. Open or show a copy in its folder to decide yourself.', style: TextStyle(fontSize: 13, color: C.muted)),
            const SizedBox(height: 18),
            for (final g in groups) ...[
              DuplicateGroupCard(group: g, api: widget.api, onOpen: widget.onOpen, onShow: widget.onShow, compact: widget.compact),
              const SizedBox(height: 12),
            ],
          ]);
        },
      );
}
