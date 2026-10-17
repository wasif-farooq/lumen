import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import '../pairing/mobile_connect.dart';
import '../pairing/pairing_store.dart';
import 'mobile_chat.dart';

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
    unawaited(_restore());
  }

  Future<void> _restore() async {
    final saved = await Pairing.load();
    if (saved != null) {
      final (base, token, _) = saved;
      state = AppState(Api(base, token: token));
      await state!.connect();
      state!.watchReminders(); // the banner for reminders that go off
    }
    if (mounted) setState(() => loading = false);
  }

  Future<void> _paired(String base, String token, String host) async {
    await Pairing.save(base, token, host);
    final s = AppState(Api(base, token: token));
    await s.connect();
    s.watchReminders();
    if (mounted) setState(() => state = s);
  }

  Future<void> _unpair() async {
    await Pairing.clear();
    state?.stopWatchingReminders();
    if (mounted) setState(() => state = null);
  }

  @override
  Widget build(BuildContext context) {
    if (loading) return const Scaffold(body: Center(child: CircularProgressIndicator(color: C.accent)));
    if (state == null) return MobileConnect(onPaired: _paired);
    return MobileChat(state: state!, onUnpair: _unpair);
  }
}
