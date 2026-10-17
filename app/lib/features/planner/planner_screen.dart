import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import 'notes_tab.dart';
import 'planner_controller.dart';
import 'reminders_tab.dart';
import 'todos_tab.dart';

/// Notes & to-dos with tabs: Notes · To-dos · Reminders. The same things can be made in chat
/// ("note: …", "add milk to my shopping list", "remind me tomorrow at 5 …").
class PlannerScreen extends StatefulWidget {
  const PlannerScreen({super.key, required this.state, this.compact = false});
  final AppState state;
  final bool compact; // phone: one column at a time

  @override
  State<PlannerScreen> createState() => _PlannerScreenState();
}

class _PlannerScreenState extends State<PlannerScreen> with SingleTickerProviderStateMixin {
  late final PlannerController c = PlannerController(widget.state)..start();
  late final TabController _tabs = TabController(length: 3, vsync: this);

  @override
  void dispose() {
    _tabs.dispose();
    c.dispose();
    super.dispose();
  }

  Widget _tab(IconData icon, String label) => Tab(
        height: 44,
        child: Row(mainAxisSize: MainAxisSize.min, children: [Icon(icon, size: 18), const SizedBox(width: 8), Text(label)]),
      );

  @override
  Widget build(BuildContext context) {
    final pad = widget.compact ? 16.0 : 32.0;
    return ListenableBuilder(
      listenable: c,
      builder: (context, _) => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Container(
          padding: EdgeInsets.fromLTRB(pad, widget.compact ? 8 : 24, pad, 0),
          decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: C.line))),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (!widget.compact) ...[
              const Text('Notes & to-dos', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
              const SizedBox(height: 12),
            ],
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
                _tab(Icons.sticky_note_2_outlined, 'Notes'),
                _tab(Icons.checklist, 'To-dos'),
                _tab(Icons.alarm, 'Reminders'),
              ],
            ),
          ]),
        ),
        if (c.loadError != null)
          Padding(
            padding: EdgeInsets.all(pad),
            child: Text('Could not load: ${c.loadError}', style: const TextStyle(color: C.red)),
          ),
        Expanded(
          child: TabBarView(controller: _tabs, children: [
            NotesTab(c: c, compact: widget.compact),
            TodosTab(c: c, compact: widget.compact),
            RemindersTab(c: c, compact: widget.compact),
          ]),
        ),
      ]),
    );
  }
}
