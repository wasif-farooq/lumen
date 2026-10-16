import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/common.dart';
import 'general_settings.dart';
import '../models/models_screen.dart';
import '../sync/sync_screen.dart';

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
