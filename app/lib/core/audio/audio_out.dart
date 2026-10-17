import 'dart:typed_data';

import 'package:flutter_soloud/flutter_soloud.dart';

/// Plays PCM16 mono audio as it arrives (the server's spoken answer, sentence by sentence).
abstract class AudioOut {
  /// Start a new stream of audio at this sample rate.
  Future<void> begin(int sampleRate);
  void add(Uint8List pcm);

  /// No more audio is coming: play what is left, then stop.
  Future<void> end();

  /// Stop at once (the user interrupted).
  Future<void> stopNow();
}

/// The real speaker, through SoLoud's buffer stream (starts playing after 0.1 s of audio).
class SoloudOut implements AudioOut {
  AudioSource? _source;
  SoundHandle? _handle;

  @override
  Future<void> begin(int sampleRate) async {
    await stopNow();
    final soloud = SoLoud.instance;
    if (!soloud.isInitialized) await soloud.init();
    final source = soloud.setBufferStream(
      sampleRate: sampleRate,
      bufferingTimeNeeds: 0.1,
      bufferingType: BufferingType.released,
      maxBufferSizeDuration: const Duration(minutes: 5),
    );
    _source = source;
    _handle = soloud.play(source);
  }

  @override
  void add(Uint8List pcm) {
    final source = _source;
    if (source != null) SoLoud.instance.addAudioDataStream(source, pcm);
  }

  @override
  Future<void> end() async {
    final source = _source;
    if (source != null) SoLoud.instance.setDataIsEnded(source);
  }

  @override
  Future<void> stopNow() async {
    final handle = _handle, source = _source;
    _handle = _source = null;
    if (handle != null) await SoLoud.instance.stop(handle);
    if (source != null) await SoLoud.instance.disposeSource(source);
  }
}
