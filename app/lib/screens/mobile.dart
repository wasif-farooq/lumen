import 'dart:async';

import 'package:flutter/material.dart';
import 'package:multicast_dns/multicast_dns.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api.dart';
import '../app_state.dart';
import '../theme.dart';
import '../widgets/chat_view.dart';
import '../widgets/common.dart';
import '../widgets/preview_panel.dart';

class Found {
  final String name, address;
  Found(this.name, this.address);
}

/// Finds laptops running `lumen serve --lan` on this Wi-Fi (mDNS).
Future<List<Found>> discover({Duration timeout = const Duration(seconds: 4)}) async {
  final client = MDnsClient();
  final found = <String, Found>{};
  try {
    await client.start();
    await for (final ptr in client.lookup<PtrResourceRecord>(ResourceRecordQuery.serverPointer('_lumen._tcp.local')).timeout(timeout, onTimeout: (s) => s.close())) {
      await for (final srv in client.lookup<SrvResourceRecord>(ResourceRecordQuery.service(ptr.domainName)).timeout(const Duration(seconds: 2), onTimeout: (s) => s.close())) {
        await for (final ip in client.lookup<IPAddressResourceRecord>(ResourceRecordQuery.addressIPv4(srv.target)).timeout(const Duration(seconds: 2), onTimeout: (s) => s.close())) {
          final name = ptr.domainName.split('.').first;
          found[name] = Found(name, '${ip.address.address}:${srv.port}');
        }
      }
    }
  } catch (_) {
    // Discovery is best effort; the user can type the address.
  } finally {
    client.stop();
  }
  return found.values.toList();
}

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
    _scan();
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
      widget.onPaired(base, r['token'], r['host'] ?? addr);
    } catch (e) {
      setState(() => error = e is ApiException && e.status == 403 ? 'Wrong or expired code. Make a new one on the laptop.' : 'Could not reach $base');
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
                  if (v.length == 6) _pair();
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

class MobileChat extends StatefulWidget {
  const MobileChat({super.key, required this.state, required this.onUnpair});
  final AppState state;
  final VoidCallback onUnpair;

  @override
  State<MobileChat> createState() => _MobileChatState();
}

class _MobileChatState extends State<MobileChat> {
  AppState get s => widget.state;

  Future<void> _open(Hit hit, {double start = 0}) async {
    try {
      final msg = await s.api.open(hit.path, start: start);
      _toast(msg.startsWith('NOT OPENED') ? 'Test mode: nothing was opened.' : 'Opened on ${s.host}${start > 0 ? ' at ${clock(start)}' : ''}');
    } catch (e) {
      _toast('$e');
    }
  }

  Future<void> _show(Hit hit) async {
    try {
      await s.api.show(hit.path);
      _toast('Folder opened on ${s.host}');
    } catch (e) {
      _toast('$e');
    }
  }

  void _toast(String m) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  void _sheet(Hit hit) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(22))),
      builder: (_) => ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.85),
        child: FileDetails(
          api: s.api,
          hit: hit,
          mobile: true,
          onOpen: (h, {double start = 0}) {
            Navigator.pop(context);
            _open(h, start: start);
          },
          onShow: () {
            Navigator.pop(context);
            _show(hit);
          },
          onAsk: (q) {
            Navigator.pop(context);
            s.send(q);
          },
          onSimilar: () {
            Navigator.pop(context);
            s.findSimilar(path: hit.path);
          },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: s,
        builder: (context, _) {
          final title = s.chats.where((c) => c.id == s.chatId).firstOrNull?.title ?? 'New chat';
          return Scaffold(
            appBar: AppBar(
              backgroundColor: C.bg,
              surfaceTintColor: Colors.transparent,
              titleSpacing: 0,
              title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                Row(children: [
                  StatusDot(size: 7, color: s.connectError == null ? C.green : C.red),
                  const SizedBox(width: 6),
                  Text('${s.host} · ${s.connectError == null ? 'connected' : 'offline'}', style: const TextStyle(fontSize: 12, color: C.text3)),
                ]),
              ]),
              actions: [IconButton(tooltip: 'New chat', onPressed: s.newChat, icon: const Icon(Icons.add))],
              bottom: const PreferredSize(preferredSize: Size.fromHeight(1), child: Divider(height: 1)),
            ),
            drawer: Drawer(
              backgroundColor: C.panel,
              child: SafeArea(
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  const Padding(
                    padding: EdgeInsets.all(20),
                    child: Row(children: [Logo(), SizedBox(width: 10), Text('Chats', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 16))]),
                  ),
                  Expanded(
                    child: ListView(children: [
                      for (final c in s.chats)
                        ListTile(
                          title: Text(c.title, maxLines: 1, overflow: TextOverflow.ellipsis),
                          selected: c.id == s.chatId,
                          selectedColor: C.text,
                          selectedTileColor: C.raised,
                          onTap: () {
                            Navigator.pop(context);
                            s.openChat(c.id);
                          },
                        ),
                    ]),
                  ),
                  ListTile(leading: const Icon(Icons.link_off), title: Text('Unpair from ${s.host}'), onTap: widget.onUnpair),
                ]),
              ),
            ),
            body: Column(children: [
              Expanded(child: ChatView(state: s, compact: true, onOpen: _open, onShow: _show, onHitTap: _sheet)),
              SafeArea(top: false, child: Composer(state: s, compact: true)),
            ]),
          );
        },
      );
}

class Pairing {
  static Future<(String, String, String)?> load() async {
    final p = await SharedPreferences.getInstance();
    final base = p.getString('base'), token = p.getString('token');
    if (base == null || token == null) return null;
    return (base, token, p.getString('host') ?? 'laptop');
  }

  static Future<void> save(String base, String token, String host) async {
    final p = await SharedPreferences.getInstance();
    await p.setString('base', base);
    await p.setString('token', token);
    await p.setString('host', host);
  }

  static Future<void> clear() async {
    final p = await SharedPreferences.getInstance();
    await p.remove('token');
  }
}
