import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../core/format.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';
import 'results.dart';

/// A video result: frames, the matching line, a timeline and "Play at".
class VideoCard extends StatelessWidget {
  const VideoCard({super.key, required this.hit, required this.api, required this.selected, required this.onSelect, required this.onOpen, required this.onShow, this.frames = 6});
  final Hit hit;
  final Api api;
  final bool selected;
  final VoidCallback onSelect, onShow;
  final HitAction onOpen;
  final int frames;

  @override
  Widget build(BuildContext context) {
    final dur = hit.duration ?? 0;
    final at = hit.at;
    final atFrame = (at != null && dur > 0) ? ((at / dur) * frames).floor().clamp(0, frames - 1) : -1;
    return Material(
      color: C.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14), side: BorderSide(color: selected ? C.accent : C.line, width: selected ? 1.5 : 1)),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onSelect,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (dur > 0)
              Row(children: [
                for (var i = 0; i < frames; i++) ...[
                  if (i > 0) const SizedBox(width: 4),
                  Expanded(
                    child: AspectRatio(
                      aspectRatio: 16 / 9,
                      child: Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(4),
                          border: i == atFrame ? Border.all(color: C.accent, width: 2) : null,
                        ),
                        clipBehavior: Clip.antiAlias,
                        child: ApiImage(api: api, path: hit.path, w: 240, t: dur * (i + 0.5) / frames),
                      ),
                    ),
                  ),
                ],
              ]),
            const SizedBox(height: 14),
            Wrap(spacing: 10, crossAxisAlignment: WrapCrossAlignment.end, children: [
              Text(hit.name, style: const TextStyle(fontWeight: FontWeight.w600)),
              Text('${clock(dur)} · ${humanSize(hit.size)}', style: const TextStyle(fontSize: 13, color: C.muted)),
            ]),
            if (at != null) ...[
              const SizedBox(height: 12),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                decoration: BoxDecoration(color: const Color(0xFF1F242A), borderRadius: BorderRadius.circular(10)),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(clock(at), style: monoStyle(size: 13, color: C.accent)),
                  const SizedBox(width: 12),
                  Expanded(child: Text('“${hit.atText}”', style: const TextStyle(fontSize: 15))),
                ]),
              ),
              const SizedBox(height: 12),
              Timeline(position: dur > 0 ? at / dur : 0),
              const SizedBox(height: 6),
              Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                Text('0:00', style: monoStyle(color: C.muted)),
                Text(clock(dur), style: monoStyle(color: C.muted)),
              ]),
            ] else if (hit.snippet.isNotEmpty) ...[
              const SizedBox(height: 6),
              Highlighted(hit.snippet, maxLines: 2),
            ],
            const SizedBox(height: 14),
            Wrap(spacing: 8, runSpacing: 8, children: [
              FilledButton.icon(
                onPressed: () => onOpen(hit, start: at ?? 0),
                icon: const Icon(Icons.play_arrow_rounded, size: 18),
                label: Text(at != null ? 'Play at ${clock(at)}' : 'Play'),
              ),
              if (at != null) OutlinedButton(onPressed: () => onOpen(hit, start: 0), child: const Text('Play from start')),
              OutlinedButton(onPressed: onShow, child: const Text('Show in folder')),
            ]),
          ]),
        ),
      ),
    );
  }
}

/// Where in a video the match is (0..1).
class Timeline extends StatelessWidget {
  const Timeline({super.key, required this.position});
  final double position; // 0..1

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, c) {
        final x = c.maxWidth * position.clamp(0, 1);
        return SizedBox(
          height: 16,
          child: Stack(clipBehavior: Clip.none, children: [
            Positioned(left: 0, right: 0, top: 5, child: Container(height: 6, decoration: BoxDecoration(color: const Color(0xFF2A2F35), borderRadius: BorderRadius.circular(3)))),
            Positioned(left: 0, top: 5, child: Container(width: x, height: 6, decoration: BoxDecoration(color: const Color(0xFF4A4136), borderRadius: BorderRadius.circular(3)))),
            Positioned(left: x - 2, top: 0, child: Container(width: 4, height: 16, decoration: BoxDecoration(color: C.accent, borderRadius: BorderRadius.circular(2)))),
          ]),
        );
      });
}
