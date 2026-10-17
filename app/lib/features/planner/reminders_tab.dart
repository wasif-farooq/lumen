import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../core/errors/run_guarded.dart';
import '../../shared/theme.dart';
import 'planner_controller.dart';
import 'planner_parts.dart';

const repeats = {'none': 'Once', 'daily': 'Every day', 'weekdays': 'Every weekday', 'weekly': 'Every week', 'monthly': 'Every month'};

/// Reminders: upcoming and repeating ones, and a form to add one (date, time, repeat).
class RemindersTab extends StatefulWidget {
  const RemindersTab({super.key, required this.c, this.compact = false});
  final PlannerController c;
  final bool compact;

  @override
  State<RemindersTab> createState() => _RemindersTabState();
}

class _RemindersTabState extends State<RemindersTab> {
  final _text = TextEditingController();
  DateTime? at; // null: in an hour
  String repeat = 'none';

  static DateTime _inAnHour() {
    final n = DateTime.now().add(const Duration(hours: 1));
    return DateTime(n.year, n.month, n.day, n.hour, n.minute);
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _pick() async {
    final day = await showDatePicker(
      context: context,
      initialDate: at ?? _inAnHour(),
      firstDate: DateTime.now().subtract(const Duration(days: 1)),
      lastDate: DateTime.now().add(const Duration(days: 365 * 3)),
    );
    if (day == null || !mounted) return;
    final time = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(at ?? _inAnHour()));
    if (time == null) return;
    setState(() => at = DateTime(day.year, day.month, day.day, time.hour, time.minute));
  }

  Future<void> _add() async {
    final text = _text.text.trim();
    if (text.isEmpty) return;
    await runGuarded(context, () => widget.c.addReminder(text, at ?? _inAnHour(), repeat), failure: 'Could not set the reminder');
    _text.clear();
    setState(() => at = null);
  }

  Future<void> _cancel(Reminder r) async {
    await runGuarded(context, () => widget.c.cancelReminder(r), failure: 'Could not cancel it');
    if (mounted) showUndo(context, 'Reminder cancelled', () => widget.c.restoreReminder(r));
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.c;
    final pad = widget.compact ? 16.0 : 24.0;
    return ListView(padding: EdgeInsets.all(pad), children: [
      Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
        SizedBox(
          width: widget.compact ? double.infinity : 320,
          child: TextField(
            controller: _text,
            onSubmitted: (_) => _add(),
            decoration: const InputDecoration(hintText: 'Remind me to…', isDense: true),
          ),
        ),
        OutlinedButton.icon(onPressed: _pick, icon: const Icon(Icons.event, size: 18), label: Text(at == null ? 'In an hour' : shortTime(at!))),
        DropdownButton<String>(
          value: repeat,
          onChanged: (v) => setState(() => repeat = v ?? 'none'),
          items: [for (final e in repeats.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
        ),
        FilledButton.icon(onPressed: _add, icon: const Icon(Icons.alarm_add, size: 18), label: const Text('Add')),
      ]),
      const SizedBox(height: 8),
      const Text('Or in chat: “remind me tomorrow at 5 to call the bank”, “every Monday at 9 to pay the rent”.',
          style: TextStyle(color: C.muted, fontSize: 12.5)),
      const SizedBox(height: 16),
      if (c.reminders.isEmpty) const Empty(icon: Icons.alarm, text: 'No reminders.'),
      for (final r in c.reminders)
        Card(
          color: C.surface,
          margin: const EdgeInsets.only(bottom: 8),
          child: ListTile(
            leading: Icon(r.repeat == 'none' ? Icons.alarm : Icons.repeat, color: C.accent),
            title: Text(r.text),
            subtitle: Text(r.when, style: const TextStyle(color: C.text3)),
            trailing: IconButton(tooltip: 'Cancel reminder', onPressed: () => _cancel(r), icon: const Icon(Icons.alarm_off, size: 20)),
          ),
        ),
    ]);
  }
}
