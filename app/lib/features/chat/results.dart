import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';
import 'video_card.dart';
import '../../core/format.dart';

typedef HitAction = void Function(Hit hit, {double start});

/// A file found by the agent (document / image row).
class ResultCard extends StatelessWidget {
  const ResultCard({
    super.key,
    required this.hit,
    required this.api,
    required this.selected,
    required this.onSelect,
    required this.onOpen,
    required this.onShow,
    this.onSimilar,
    this.compact = false,
  });

  final Hit hit;
  final Api api;
  final bool selected, compact;
  final VoidCallback onSelect, onShow;
  final VoidCallback? onSimilar;
  final HitAction onOpen;

  @override
  Widget build(BuildContext context) {
    if (hit.kind == 'video' && !compact) return VideoCard(hit: hit, api: api, selected: selected, onSelect: onSelect, onOpen: onOpen, onShow: onShow);
    final leading = hit.kind == 'image'
        ? ClipRRect(borderRadius: BorderRadius.circular(6), child: SizedBox(width: compact ? 36 : 40, height: compact ? 44 : 48, child: ApiImage(api: api, path: hit.path, w: 96)))
        : FileBadge(kind: hit.kind, ext: hit.ext, width: compact ? 36 : 40, height: compact ? 44 : 48);
    final quote = hit.at != null ? '${clock(hit.at!)}  “${hit.atText}”' : hit.snippet;
    return Material(
      color: C.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: selected ? C.accent : C.line, width: selected ? 1.5 : 1),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onSelect,
        child: Padding(
          padding: EdgeInsets.all(compact ? 12 : 14),
          child: Row(crossAxisAlignment: compact ? CrossAxisAlignment.center : CrossAxisAlignment.start, children: [
            leading,
            const SizedBox(width: 14),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Wrap(spacing: 10, crossAxisAlignment: WrapCrossAlignment.end, children: [
                  Text(hit.name, style: const TextStyle(fontWeight: FontWeight.w600), overflow: TextOverflow.ellipsis),
                  if (!compact)
                    Text(
                      '${hit.duration != null ? '${clock(hit.duration!)} · ' : ''}${humanSize(hit.size)} · ${humanDate(hit.mtime)}',
                      style: const TextStyle(fontSize: 13, color: C.muted),
                    ),
                ]),
                if (!compact) ...[
                  const SizedBox(height: 3),
                  Text(shortPath(hit.path), style: monoStyle(), maxLines: 1, overflow: TextOverflow.ellipsis),
                ],
                if (quote.isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Highlighted(quote, maxLines: compact ? 1 : 2),
                ],
              ]),
            ),
            if (compact)
              const Icon(Icons.chevron_right, color: C.muted)
            else ...[
              const SizedBox(width: 10),
              selected
                  ? FilledButton(onPressed: () => onOpen(hit, start: hit.at ?? 0), style: _small, child: const Text('Open'))
                  : OutlinedButton(onPressed: () => onOpen(hit, start: hit.at ?? 0), style: _smallOutline, child: const Text('Open')),
              if (hit.kind == 'image' && onSimilar != null) ...[
                const SizedBox(width: 6),
                IconButton(
                  tooltip: 'Find similar images',
                  onPressed: onSimilar,
                  style: IconButton.styleFrom(side: const BorderSide(color: C.line2), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8))),
                  icon: const Icon(Icons.image_search, size: 18, color: C.text2),
                ),
              ],
              const SizedBox(width: 6),
              IconButton(
                tooltip: 'Show in folder',
                onPressed: onShow,
                style: IconButton.styleFrom(side: const BorderSide(color: C.line2), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8))),
                icon: const Icon(Icons.folder_open_outlined, size: 18, color: C.text2),
              ),
            ],
          ]),
        ),
      ),
    );
  }
}

final _small = FilledButton.styleFrom(minimumSize: const Size(64, 36), padding: const EdgeInsets.symmetric(horizontal: 14), textStyle: const TextStyle(fontFamily: sans, fontSize: 13, fontWeight: FontWeight.w600));
final _smallOutline = OutlinedButton.styleFrom(minimumSize: const Size(64, 36), padding: const EdgeInsets.symmetric(horizontal: 14), textStyle: const TextStyle(fontFamily: sans, fontSize: 13));
