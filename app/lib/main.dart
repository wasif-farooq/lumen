import 'dart:io';

import 'package:flutter/material.dart';

import 'api.dart';
import 'app_state.dart';
import 'screens/desktop_shell.dart';
import 'screens/mobile.dart';
import 'theme.dart';
import 'widgets/common.dart';
import 'widgets/zoom.dart';

void main() => runApp(const LumenApp());

bool get isDesktop => Platform.isLinux || Platform.isMacOS || Platform.isWindows;

class LumenApp extends StatelessWidget {
  const LumenApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Lumen',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(),
        builder: isDesktop ? (context, child) => Zoom(child: child!) : null,
        home: isDesktop ? const DesktopHome() : const MobileHome(),
      );
}

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

  String get projectDir =>
      Platform.environment['LUMEN_HOME'] ?? Platform.environment['OS_OPERATOR_HOME'] ?? '${Platform.environment['HOME']}/work/personal/os-operator';

  @override
  void initState() {
    super.initState();
    _connect();
  }

  Future<void> _connect() async {
    final ok = await state.connect();
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
                ? const CircularProgressIndicator(color: C.accent)
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

/// Mobile: pair once with the laptop, then chat.
class MobileHome extends StatefulWidget {
  const MobileHome({super.key});
  @override
  State<MobileHome> createState() => _MobileHomeState();
}

class _MobileHomeState extends State<MobileHome> {
  AppState? state;
  bool loading = true;

  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    final saved = await Pairing.load();
    if (saved != null) {
      final (base, token, _) = saved;
      state = AppState(Api(base, token: token));
      await state!.connect();
    }
    if (mounted) setState(() => loading = false);
  }

  Future<void> _paired(String base, String token, String host) async {
    await Pairing.save(base, token, host);
    final s = AppState(Api(base, token: token));
    await s.connect();
    if (mounted) setState(() => state = s);
  }

  Future<void> _unpair() async {
    await Pairing.clear();
    if (mounted) setState(() => state = null);
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Scaffold(body: Center(child: CircularProgressIndicator(color: C.accent)));
    if (state == null) return MobileConnect(onPaired: _paired);
    return MobileChat(state: state!, onUnpair: _unpair);
  }
}
