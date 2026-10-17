import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../core/format.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';

/// Video and audio. Until in-app playback is in (docs/VIEWER.md, step 3): a frame and the transcript
/// around the found moment, and playing on the laptop at that moment.
class MediaView extends StatefulWidget {
  const MediaView({super.key, required this.api, required this.info, this.at, required this.onPlayOnLaptop});
  final Api api;
  final ViewInfo info;
  final double? at;
  final void Function(double start) onPlayOnLaptop;

  @override
  State<MediaView> createState() => _MediaViewState();
}

class _MediaViewState extends State<MediaView> {
  late final Future<FileInfo> details = widget.api.file(widget.info.path, at: widget.at);

  @override
  Widget build(BuildContext context) {
    final at = widget.at ?? 0;
    return ListView(padding: const EdgeInsets.all(24), children: [
      if (widget.info.kind == 'video')
        Center(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: SizedBox(width: 640, child: ApiImage(api: widget.api, path: widget.info.path, w: 960, t: at > 0 ? at : null)),
          ),
        ),
      const SizedBox(height: 16),
      Center(
        child: FilledButton.icon(
          onPressed: () => widget.onPlayOnLaptop(at),
          icon: const Icon(Icons.play_arrow),
          label: Text(at > 0 ? 'Play on the laptop at ${clock(at)}' : 'Play on the laptop'),
        ),
      ),
      const SizedBox(height: 20),
      FutureBuilder<FileInfo>(
        future: details,
        builder: (context, snap) {
          final segments = snap.data?.segments ?? const [];
          if (segments.isEmpty) return const SizedBox.shrink();
          return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('What is said', style: TextStyle(fontSize: 13, color: C.muted)),
            const SizedBox(height: 8),
            for (final s in segments)
              InkWell(
                onTap: () => widget.onPlayOnLaptop(s.start),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 5),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    SizedBox(width: 64, child: Text(s.time, style: monoStyle(size: 12.5, color: (s.start - at).abs() < 1 ? C.accent : C.muted))),
                    Expanded(child: Text(s.text, style: TextStyle(color: (s.start - at).abs() < 1 ? C.text : C.text2))),
                  ]),
                ),
              ),
          ]);
        },
      ),
    ]);
  }
}
