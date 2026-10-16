import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/cards.dart';
import '../../shared/widgets/common.dart';
import '../sync/sync_screen.dart';
import '../models/models_screen.dart';

/// Settings with tabs: General · Models · Sync.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.state, this.tab = 0, this.onTab});
  final AppState state;
  final int tab; // 0 General, 1 Models, 2 Sync
  final ValueChanged<int>? onTab;

  static const tabs = ['General', 'Models', 'Sync'];

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: SettingsScreen.tabs.length, vsync: this, initialIndex: widget.tab)
    ..addListener(_onTabChanged);
  // Tabs are built the first time they are shown and then kept, so going back to one
  // doesn't reload it.
  late final Set<int> _opened = {widget.tab};

  void _onTabChanged() {
    final i = _tabs.index;
    _opened.add(i);
    if (mounted) setState(() {});
    if (i != widget.tab) widget.onTab?.call(i);
  }

  @override
  void didUpdateWidget(SettingsScreen old) {
    super.didUpdateWidget(old);
    // Only follow the parent when it asks for a different tab (e.g. the sidebar's sync tile).
    // Ordinary rebuilds, like a status refresh, must not pull the user back to the old tab.
    if (widget.tab != old.tab && widget.tab != _tabs.index) _tabs.animateTo(widget.tab);
  }

  Widget _tab(IconData icon, String label, {Widget? dot}) => Tab(
        height: 44,
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 18),
          const SizedBox(width: 8),
          Text(label),
          if (dot != null) ...[const SizedBox(width: 8), dot],
        ]),
      );

  @override
  void dispose() {
    _tabs.removeListener(_onTabChanged);
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final st = widget.state.status ?? {};
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Container(
        padding: const EdgeInsets.fromLTRB(32, 24, 32, 0),
        decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: C.line))),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Settings', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
          const SizedBox(height: 12),
          TabBar(
            controller: _tabs,
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            labelColor: C.text,
            unselectedLabelColor: C.text3,
            indicatorColor: C.accent,
            dividerColor: Colors.transparent,
            labelStyle: const TextStyle(fontFamily: sans, fontSize: 14, fontWeight: FontWeight.w600),
            unselectedLabelStyle: const TextStyle(fontFamily: sans, fontSize: 14, fontWeight: FontWeight.w500),
            tabs: [
              _tab(Icons.tune, 'General'),
              _tab(Icons.hub_outlined, 'Models'),
              _tab(Icons.sync, 'Sync',
                  dot: st['indexing'] == true ? StatusDot(color: st['index_paused'] == true ? C.blue : C.accent) : null),
            ],
          ),
        ]),
      ),
      Expanded(
        child: IndexedStack(index: _tabs.index, sizing: StackFit.expand, children: [
          for (final (i, page) in [
            () => GeneralSettings(state: widget.state),
            () => ModelsScreen(state: widget.state, embedded: true),
            () => IndexScreen(state: widget.state, embedded: true),
          ].indexed)
            _opened.contains(i) ? page() : const SizedBox.shrink(),
        ]),
      ),
    ]);
  }
}

/// General settings: what gets indexed, power use, tracing and paired phones.
class GeneralSettings extends StatefulWidget {
  const GeneralSettings({super.key, required this.state});
  final AppState state;

  @override
  State<GeneralSettings> createState() => _GeneralSettingsState();
}

class _GeneralSettingsState extends State<GeneralSettings> {
  Map<String, dynamic>? settings;
  List<dynamic> devices = [];
  String? error;

  AppState get s => widget.state;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await Future.wait([s.api.settings(), s.api.devices().catchError((_) => <Map<String, dynamic>>[])]);
      await s.refreshStatus();
      if (!mounted) return;
      setState(() {
        settings = r[0] as Map<String, dynamic>;
        devices = r[1] as List<dynamic>;
      });
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    }
  }

  Future<void> _set(String key, Object value) async {
    setState(() => settings = {...?settings, key: value});
    try {
      final saved = await s.api.saveSettings({key: value});
      await s.refreshStatus();
      if (mounted) setState(() => settings = saved);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not save: $e')));
    }
  }

  Future<void> _pairPhone() async {
    try {
      final r = await s.api.pairStart();
      if (!mounted) return;
      await showDialog(context: context, builder: (_) => _PairDialog(code: r['code'], address: r['address'], lan: r['lan'] == true));
      final d = await s.api.devices();
      if (mounted) setState(() => devices = d);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: s,
      builder: (context, _) {
        final st = s.status ?? {};
        final pw = st['power'] ?? {};
        return ListView(
          padding: const EdgeInsets.fromLTRB(32, 20, 32, 40),
          children: [
            const Text('Saved as you change them. New indexing settings apply from the next run.', style: TextStyle(color: C.text3)),
            if (error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(error!, style: const TextStyle(color: C.red))),
            const SizedBox(height: 24),
            TwoColumns(children: [
              CardColumn(children: [
                SectionCard(
                  title: 'What gets indexed',
                  child: Column(children: [
                    const _Toggle(title: 'Document text', subtitle: 'PDF, Word, text and code. Cheap, runs on battery too.', value: true),
                    _Toggle(title: 'Describe images and scans', subtitle: 'The vision model writes what each picture shows.', value: settings?['captions'] ?? true, onChanged: (v) => _set('captions', v)),
                    _Toggle(title: 'Describe videos', subtitle: 'Six frames per video, one description.', value: settings?['media'] ?? true, onChanged: (v) => _set('media', v)),
                    _Toggle(title: 'Transcribe speech', subtitle: 'Whisper on the CPU, with timestamps.', value: settings?['transcripts'] ?? true, onChanged: (v) => _set('transcripts', v)),
                  ]),
                ),
                SectionCard(
                  title: 'Power',
                  trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                    Icon(pw['on_ac'] == true ? Icons.power_outlined : Icons.battery_std_outlined, size: 16, color: pw['on_ac'] == true ? C.green : C.accent),
                    const SizedBox(width: 6),
                    Text('${pw['on_ac'] == true ? 'Plugged in' : 'On battery'}${pw['battery'] != null ? ' · ${pw['battery']}%' : ''}',
                        style: TextStyle(fontSize: 13, color: pw['on_ac'] == true ? C.green : C.accent)),
                  ]),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('Indexing mode', style: TextStyle(fontSize: 13, color: C.muted)),
                    const SizedBox(height: 8),
                    for (final (id, name, desc) in const [
                      ('auto', 'Auto', 'AI work only when plugged in. Unplug and it pauses after the current file.'),
                      ('saver', 'Saver', 'Files and document text only. No models.'),
                      ('performance', 'Performance', 'Everything, all cores, even on battery.'),
                    ])
                      _ModeOption(name: name, desc: desc, selected: (settings?['power_mode'] ?? 'auto') == id, onTap: () => _set('power_mode', id)),
                    if (pw['ai_allowed'] == false && (pw['reason'] ?? '').toString().isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 4, bottom: 8),
                        child: Text('AI work paused: ${pw['reason']}', style: const TextStyle(fontSize: 13, color: C.accent)),
                      ),
                    _Toggle(
                      title: 'Run models on CPU only',
                      subtitle: 'Keeps the GPU free. Chat was about 15× slower in our benchmark.',
                      value: settings?['cpu_only'] ?? false,
                      onChanged: (v) => _set('cpu_only', v),
                    ),
                    Row(children: [
                      const Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text('CPU threads for indexing'),
                          Text('Fewer threads, cooler laptop.', style: TextStyle(fontSize: 13, color: C.muted)),
                        ]),
                      ),
                      _Stepper(
                        value: (settings?['threads'] ?? 4) as int,
                        onChanged: (v) => _set('threads', v),
                      ),
                    ]),
                  ]),
                ),
              ]),
              CardColumn(children: [
                SectionCard(
                  title: 'Paired phones',
                  trailing: OutlinedButton(onPressed: _pairPhone, style: OutlinedButton.styleFrom(minimumSize: const Size(0, 36)), child: const Text('Pair a phone')),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    if (st['lan'] != true)
                      const Padding(
                        padding: EdgeInsets.only(bottom: 8),
                        child: Text('Phones can only connect when the server runs with --lan.', style: TextStyle(fontSize: 13, color: C.accent)),
                      ),
                    if (devices.isEmpty) const Text('No phones paired.', style: TextStyle(fontSize: 13, color: C.muted)),
                    for (final d in devices)
                      Row(children: [
                        const Icon(Icons.smartphone, size: 18, color: C.text3),
                        const SizedBox(width: 10),
                        Expanded(child: Text('${d['name']}')),
                        TextButton(
                          onPressed: () async {
                            await s.api.unpair(d['id']);
                            final list = await s.api.devices();
                            if (mounted) setState(() => devices = list);
                          },
                          child: const Text('Remove'),
                        ),
                      ]),
                  ]),
                ),
              ]),
            ]),
          ],
        );
      },
    );
  }
}

class _Toggle extends StatelessWidget {
  const _Toggle({required this.title, required this.subtitle, required this.value, this.onChanged});
  final String title, subtitle;
  final bool value;
  final ValueChanged<bool>? onChanged;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title),
              Text(subtitle, style: const TextStyle(fontSize: 13, color: C.muted)),
            ]),
          ),
          const SizedBox(width: 12),
          Switch(value: value, onChanged: onChanged),
        ]),
      );
}

class _ModeOption extends StatelessWidget {
  const _ModeOption({required this.name, required this.desc, required this.selected, required this.onTap});
  final String name, desc;
  final bool selected;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Material(
          color: selected ? C.accentSoft : Colors.transparent,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
            side: BorderSide(color: selected ? C.accent : const Color(0xFF2A2F35), width: selected ? 1.5 : 1),
          ),
          child: InkWell(
            borderRadius: BorderRadius.circular(10),
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(selected ? Icons.radio_button_checked : Icons.radio_button_off, size: 18, color: selected ? C.accent : C.muted),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(name, style: const TextStyle(fontWeight: FontWeight.w500)),
                    Text(desc, style: const TextStyle(fontSize: 13, color: C.text3)),
                  ]),
                ),
              ]),
            ),
          ),
        ),
      );
}

class _Stepper extends StatelessWidget {
  const _Stepper({required this.value, required this.onChanged});
  final int value;
  final ValueChanged<int> onChanged;
  @override
  Widget build(BuildContext context) => Container(
        decoration: BoxDecoration(border: Border.all(color: C.line2), borderRadius: BorderRadius.circular(10)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          IconButton(tooltip: 'Fewer threads', onPressed: value > 1 ? () => onChanged(value - 1) : null, icon: const Icon(Icons.remove, size: 18)),
          SizedBox(width: 28, child: Text('$value', textAlign: TextAlign.center, style: monoStyle(size: 14, color: C.text))),
          IconButton(tooltip: 'More threads', onPressed: value < 32 ? () => onChanged(value + 1) : null, icon: const Icon(Icons.add, size: 18)),
        ]),
      );
}

class _PairDialog extends StatefulWidget {
  const _PairDialog({required this.code, required this.address, required this.lan});
  final String code, address;
  final bool lan;
  @override
  State<_PairDialog> createState() => _PairDialogState();
}

class _PairDialogState extends State<_PairDialog> {
  int left = 120;
  Timer? t;
  @override
  void initState() {
    super.initState();
    t = Timer.periodic(const Duration(seconds: 1), (_) {
      if (left <= 1) Navigator.of(context).maybePop();
      setState(() => left--);
    });
  }

  @override
  void dispose() {
    t?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Pair a phone'),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Open Lumen on your phone, pick this laptop, and enter:', style: TextStyle(color: C.text3)),
          const SizedBox(height: 18),
          Text(widget.code.split('').join(' '), style: monoStyle(size: 36, color: C.accent, weight: FontWeight.w500)),
          const SizedBox(height: 12),
          Text('Address: ${widget.address}', style: monoStyle(size: 13, color: C.text2)),
          const SizedBox(height: 6),
          Text('Code expires in $left s', style: const TextStyle(fontSize: 13, color: C.muted)),
          if (!widget.lan)
            const Padding(
              padding: EdgeInsets.only(top: 12),
              child: Text('The server is not on the network. Restart it with: lumen serve --lan', style: TextStyle(fontSize: 13, color: C.accent)),
            ),
        ]),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Done'))],
      );
}
