import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';

/// An image at full size for the screen: pinch or scroll to zoom, drag to pan, double-tap to zoom
/// in or back; swipe (or the bar's arrows) for the previous / next result.
class ImageView extends StatefulWidget {
  const ImageView({super.key, required this.api, required this.info, required this.onSwipe});
  final Api api;
  final ViewInfo info;
  final void Function(int step) onSwipe;

  @override
  State<ImageView> createState() => _ImageViewState();
}

class _ImageViewState extends State<ImageView> {
  final _zoom = TransformationController();
  TapDownDetails? _tap;

  @override
  void dispose() {
    _zoom.dispose();
    super.dispose();
  }

  void _toggle() {
    if (_zoom.value.getMaxScaleOnAxis() > 1.01) {
      _zoom.value = Matrix4.identity();
      return;
    }
    final at = _tap?.localPosition ?? Offset.zero;
    _zoom.value = Matrix4.identity()
      ..translateByDouble(-at.dx * 1.5, -at.dy * 1.5, 0, 1)
      ..scaleByDouble(2.5, 2.5, 1, 1);
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(builder: (context, box) {
        final px = (box.maxWidth * MediaQuery.devicePixelRatioOf(context)).round();
        final w = const [800, 1600, 2400, 3200, 4096].firstWhere((s) => s >= px, orElse: () => 4096);
        return GestureDetector(
          onDoubleTapDown: (d) => _tap = d,
          onDoubleTap: _toggle,
          onHorizontalDragEnd: (d) {
            if (_zoom.value.getMaxScaleOnAxis() > 1.01) return; // zoomed in: dragging pans
            final v = d.primaryVelocity ?? 0;
            if (v.abs() > 300) widget.onSwipe(v < 0 ? 1 : -1);
          },
          child: Container(
            color: const Color(0xFF0B0D0F),
            child: InteractiveViewer(
              transformationController: _zoom,
              minScale: 1,
              maxScale: 8,
              child: Center(
                child: Image.network(
                  widget.api.imageUrl(widget.info.path, w: w),
                  headers: widget.api.headers,
                  fit: BoxFit.contain,
                  loadingBuilder: (context, child, progress) =>
                      progress == null ? child : const Center(child: CircularProgressIndicator(color: C.accent)),
                  errorBuilder: (_, _, _) => const Icon(Icons.broken_image_outlined, size: 40, color: C.muted),
                ),
              ),
            ),
          ),
        );
      });
}
