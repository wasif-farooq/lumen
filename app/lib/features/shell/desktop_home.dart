import 'dart:io';

import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';
import 'desktop_shell.dart';

/// Desktop: talk to the server on this machine; offer to start it when it isn't running.
class DesktopHome extends StatefulWidget {
  const DesktopHome({super.key});
  @override
  State<DesktopHome> createState() => _DesktopHomeState();
}

class _DesktopHomeState extends State<DesktopHome> {
  final state = AppState(Api(Platform.environment['LUMEN_URL'] ?? Platform.environment['OS_OPERATOR_URL'] ?? 'http://127.0.0.1:8765'));
  bool? connected;
  bool starting = false;

  // Set by the packaged launcher (.deb / AppImage), which starts the bundled server itself
  static final _launcherStarting = Platform.environment['LUMEN_SERVER_STARTING'] == '1';
  static final _serverLog = Platform.environment['LUMEN_SERVER_LOG'];
  bool get _packaged => _serverLog != null;

  String get projectDir =>
      Platform.environment['LUMEN_HOME'] ?? Platform.environment['OS_OPERATOR_HOME'] ?? '${Platform.environment['HOME']}/work/personal/os-operator';

  @override
  void initState() {
    super.initState();
    _connect();
  }

  Future<void> _connect() async {
    var ok = await state.connect();
    // The launcher just started the server: it needs a few seconds to load before it answers
    for (var i = 0; !ok && _launcherStarting && connected == null && i < 90 && mounted; i++) {
      await Future.delayed(const Duration(milliseconds: 500));
      ok = await state.connect();
    }
    if (mounted) setState(() => connected = ok);
  }

  /// Starts `lumen serve --lan` from the project folder, detached from the app.
  Future<void> _startServer() async {
    setState(() => starting = true);
    try {
      final uv = ['${Platform.environment['HOME']}/.local/bin/uv', 'uv'].firstWhere((p) => p == 'uv' || File(p).existsSync());
      await Process.start(
        uv,
        ['run', '--env-file', '.env', 'lumen', 'serve', '--lan'],
        workingDirectory: projectDir,
        environment: {'LUMEN_DATA': '$projectDir/data'},
        mode: ProcessStartMode.detached,
      );
      for (var i = 0; i < 20 && mounted; i++) {
        await Future.delayed(const Duration(milliseconds: 750));
        if (await state.connect()) break;
      }
    } catch (e) {
      state.connectError = 'Could not start the server: $e';
    }
    if (mounted) {
      setState(() {
        starting = false;
        connected = state.connectError == null;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (connected == true) return DesktopShell(state: state);
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: connected == null
                ? const Column(mainAxisSize: MainAxisSize.min, children: [
                    CircularProgressIndicator(color: C.accent),
                    SizedBox(height: 16),
                    Text('Starting Lumen…', style: TextStyle(color: C.text3)),
                  ])
                : _packaged
                    ? Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Logo(size: 40),
                        const SizedBox(height: 18),
                        const Text('Lumen’s background service didn’t start', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
                        const SizedBox(height: 8),
                        Text('Its log may say why:\n$_serverLog\n\nClosing and reopening Lumen starts it again.',
                            style: monoStyle(size: 13, color: C.text2)),
                        const SizedBox(height: 24),
                        OutlinedButton(onPressed: _connect, child: const Text('Try again')),
                      ])
                    : Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Logo(size: 40),
                    const SizedBox(height: 18),
                    const Text('The Lumen service isn’t running', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 8),
                    Text('Start it here, or in a terminal:\n\ncd $projectDir\nuv run --env-file .env lumen serve --lan',
                        style: monoStyle(size: 13, color: C.text2)),
                    if (state.connectError != null) ...[
                      const SizedBox(height: 12),
                      Text(state.connectError!, style: const TextStyle(fontSize: 12, color: C.muted)),
                    ],
                    const SizedBox(height: 24),
                    Row(children: [
                      FilledButton(onPressed: starting ? null : _startServer, child: Text(starting ? 'Starting…' : 'Start service')),
                      const SizedBox(width: 10),
                      OutlinedButton(onPressed: starting ? null : _connect, child: const Text('Try again')),
                    ]),
                  ]),
          ),
        ),
      ),
    );
  }
}
