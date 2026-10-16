import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';
import 'discovery.dart';

/// Phone: find the laptop on this Wi-Fi (or type its address) and pair with the 6-digit code.
class MobileConnect extends StatefulWidget {
  const MobileConnect({super.key, required this.onPaired});
  final void Function(String base, String token, String host) onPaired;

  @override
  State<MobileConnect> createState() => _MobileConnectState();
}

class _MobileConnectState extends State<MobileConnect> {
  List<Found> found = [];
  bool searching = true;
  String? address;
  final _addr = TextEditingController();
  final _code = TextEditingController();
  bool manual = false, pairing = false;
  String? error;

  @override
  void initState() {
    super.initState();
    unawaited(_scan());
  }

  Future<void> _scan() async {
    setState(() => searching = true);
    final list = await discover();
    if (!mounted) return;
    setState(() {
      found = list;
      searching = false;
      if (list.length == 1) address ??= list.first.address;
    });
  }

  Future<void> _pair() async {
    final addr = manual ? _addr.text.trim() : address;
    if (addr == null || addr.isEmpty) return setState(() => error = 'Pick your laptop or type its address.');
    final base = addr.startsWith('http') ? addr : 'http://${addr.contains(':') ? addr : '$addr:8765'}';
    setState(() {
      pairing = true;
      error = null;
    });
    try {
      final r = await Api(base).pair(_code.text.trim(), 'Phone');
      widget.onPaired(base, '${r['token']}', '${r['host'] ?? addr}');
    } on ApiError catch (e) {
      setState(() => error = switch (e) {
            ApiError(status: 403) => 'Wrong or expired code. Make a new one on the laptop.',
            ApiError(isConnection: true) => 'Could not reach $base',
            _ => e.message,
          });
    } finally {
      if (mounted) setState(() => pairing = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(24, 24, 24, 32),
            children: [
              const Row(children: [Logo(), SizedBox(width: 10), Text('Lumen', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 16))]),
              const SizedBox(height: 28),
              const Text('Connect to your laptop', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w600, height: 1.2)),
              const SizedBox(height: 8),
              const Text('Your files stay on the laptop. This phone sends questions and shows the answers.', style: TextStyle(color: C.text3, fontSize: 15)),
              const SizedBox(height: 28),
              Row(children: [
                Text(searching ? 'Looking on this Wi-Fi…' : 'Found on this Wi-Fi', style: const TextStyle(fontSize: 13, color: C.muted)),
                const Spacer(),
                if (!searching) TextButton(onPressed: _scan, child: const Text('Search again')),
              ]),
              const SizedBox(height: 6),
              if (searching) const LinearProgressIndicator(color: C.accent, backgroundColor: C.surface),
              for (final f in found)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Material(
                    color: address == f.address && !manual ? const Color(0xFF1A1812) : C.surface,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                      side: BorderSide(color: address == f.address && !manual ? C.accent : C.line, width: 1.5),
                    ),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(14),
                      onTap: () => setState(() {
                        address = f.address;
                        manual = false;
                      }),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Row(children: [
                          const Icon(Icons.laptop, color: C.accent, size: 28),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text(f.name, style: const TextStyle(fontWeight: FontWeight.w600)),
                              Text(f.address, style: monoStyle(size: 13)),
                            ]),
                          ),
                          const StatusDot(size: 10),
                        ]),
                      ),
                    ),
                  ),
                ),
              if (!searching && found.isEmpty && !manual)
                const Text('No laptop found. Start it with “lumen serve --lan”, or enter the address.', style: TextStyle(color: C.text3, fontSize: 13)),
              if (manual) ...[
                const SizedBox(height: 8),
                TextField(
                  controller: _addr,
                  keyboardType: TextInputType.url,
                  style: monoStyle(size: 15, color: C.text),
                  decoration: _boxed('Laptop address, e.g. 192.168.1.24:8765'),
                ),
              ],
              const SizedBox(height: 24),
              const Text('Enter the 6-digit code shown on the laptop', style: TextStyle(fontSize: 13, color: C.muted)),
              const SizedBox(height: 10),
              TextField(
                controller: _code,
                keyboardType: TextInputType.number,
                maxLength: 6,
                textAlign: TextAlign.center,
                style: monoStyle(size: 28, color: C.text).copyWith(letterSpacing: 14),
                decoration: _boxed('······').copyWith(counterText: ''),
                onChanged: (v) {
                  if (v.length == 6) unawaited(_pair());
                },
              ),
              if (error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(error!, style: const TextStyle(color: C.red))),
              const SizedBox(height: 32),
              FilledButton(
                onPressed: pairing ? null : _pair,
                style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
                child: Text(pairing ? 'Pairing…' : 'Pair phone'),
              ),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: () => setState(() => manual = !manual),
                style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
                child: Text(manual ? 'Pick from the list' : 'Enter address manually'),
              ),
            ],
          ),
        ),
      );

  InputDecoration _boxed(String hint) => InputDecoration(
        hintText: hint,
        filled: true,
        fillColor: C.surface,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFF3A4048))),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: Color(0xFF3A4048))),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: C.accent)),
      );
}
