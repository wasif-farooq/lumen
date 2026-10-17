import 'dart:async';
import 'dart:typed_data';

import 'package:record/record.dart';

/// Why the microphone can't be used, in words people can act on.
class MicrophoneError implements Exception {
  MicrophoneError(this.message);
  final String message;
  @override
  String toString() => message;
}

/// The microphone as a stream of PCM16 mono audio at 16 kHz (what the voice server listens to).
abstract class Microphone {
  Future<Stream<Uint8List>> start();
  Future<void> stop();
}

/// The real microphone (the `record` package; on Linux it records with parecord).
class RecordMicrophone implements Microphone {
  final _recorder = AudioRecorder();

  @override
  Future<Stream<Uint8List>> start() async {
    if (!await _recorder.hasPermission()) {
      throw MicrophoneError('Lumen may not use the microphone. Allow it in the system settings.');
    }
    try {
      return await _recorder.startStream(const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: 16000,
        numChannels: 1,
        echoCancel: true, // so the answer from the speakers isn't heard as a question
        noiseSuppress: true,
      ));
    } on Exception catch (e) {
      throw MicrophoneError('The microphone could not be opened ($e).');
    }
  }

  @override
  Future<void> stop() => _recorder.stop();
}
