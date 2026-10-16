import 'dart:async';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../theme.dart';

/// Browser-style zoom for the whole desktop UI: Ctrl +/-, Ctrl 0, Ctrl + mouse wheel.
/// The level is remembered between runs.
class Zoom extends StatefulWidget {
  const Zoom({super.key, required this.child});
  final Widget child;

  @override
  State<Zoom> createState() => _ZoomState();
}

class _ZoomState extends State<Zoom> {
  static const _min = 0.5, _max = 2.0, _step = 0.1, _key = 'zoom';
  double zoom = 1.0;
  bool _showLevel = false;
  Timer? _hide;

  @override
  void initState() {
    super.initState();
    HardwareKeyboard.instance.addHandler(_onKey);
    unawaited(SharedPreferences.getInstance().then((p) {
      final saved = p.getDouble(_key);
      if (saved != null && mounted) setState(() => zoom = saved.clamp(_min, _max));
    }));
  }

  @override
  void dispose() {
    HardwareKeyboard.instance.removeHandler(_onKey);
    _hide?.cancel();
    super.dispose();
  }

  void _set(double z) {
    z = (z.clamp(_min, _max) * 10).round() / 10;
    if (z == zoom) return;
    setState(() {
      zoom = z;
      _showLevel = true;
    });
    _hide?.cancel();
    _hide = Timer(const Duration(milliseconds: 1200), () {
      if (mounted) setState(() => _showLevel = false);
    });
    unawaited(SharedPreferences.getInstance().then((p) => p.setDouble(_key, z)));
  }

  bool _onKey(KeyEvent e) {
    if (e is! KeyDownEvent && e is! KeyRepeatEvent) return false;
    if (!HardwareKeyboard.instance.isControlPressed) return false;
    final k = e.logicalKey;
    if (k == LogicalKeyboardKey.equal || k == LogicalKeyboardKey.add || k == LogicalKeyboardKey.numpadAdd) {
      _set(zoom + _step);
    } else if (k == LogicalKeyboardKey.minus || k == LogicalKeyboardKey.numpadSubtract) {
      _set(zoom - _step);
    } else if (k == LogicalKeyboardKey.digit0 || k == LogicalKeyboardKey.numpad0) {
      _set(1.0);
    } else {
      return false;
    }
    return true;
  }

  void _onPointer(PointerSignalEvent e) {
    if (e is PointerScrollEvent && HardwareKeyboard.instance.isControlPressed) {
      GestureBinding.instance.pointerSignalResolver.register(e, (_) {
        _set(zoom + (e.scrollDelta.dy < 0 ? _step : -_step));
      });
    }
  }

  @override
  Widget build(BuildContext context) => Listener(
        onPointerSignal: _onPointer,
        child: LayoutBuilder(builder: (context, c) {
          // Lay the UI out in a smaller/larger virtual window, then scale it to the real one
          final size = Size(c.maxWidth / zoom, c.maxHeight / zoom);
          final mq = MediaQuery.of(context);
          return Stack(children: [
            SizedBox.expand(
              child: FittedBox(
                fit: BoxFit.fill,
                alignment: Alignment.topLeft,
                child: SizedBox.fromSize(
                  size: size,
                  child: MediaQuery(data: mq.copyWith(size: size), child: widget.child),
                ),
              ),
            ),
            if (_showLevel)
              Positioned(
                top: 16,
                right: 16,
                child: IgnorePointer(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                    decoration: BoxDecoration(color: C.raised, borderRadius: BorderRadius.circular(10), border: Border.all(color: C.line2)),
                    child: Text('${(zoom * 100).round()}%', style: const TextStyle(color: C.text, fontSize: 14, decoration: TextDecoration.none, fontFamily: sans)),
                  ),
                ),
              ),
          ]);
        }),
      );
}
