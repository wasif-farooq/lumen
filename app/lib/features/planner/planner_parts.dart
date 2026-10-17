import 'dart:async';

import 'package:flutter/material.dart';

import '../../shared/theme.dart';

/// Nothing here yet.
class Empty extends StatelessWidget {
  const Empty({super.key, required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, size: 32, color: C.muted),
            const SizedBox(height: 10),
            Text(text, textAlign: TextAlign.center, style: const TextStyle(color: C.text3)),
          ]),
        ),
      );
}

/// Ask for one line of text; null when cancelled or empty.
Future<String?> askText(BuildContext context, String title, String label, {String initial = ''}) async {
  final ctrl = TextEditingController(text: initial);
  final value = await showDialog<String>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: ctrl,
        autofocus: true,
        decoration: InputDecoration(labelText: label),
        onSubmitted: (v) => Navigator.pop(context, v),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(context, ctrl.text), child: const Text('OK')),
      ],
    ),
  );
  ctrl.dispose();
  return (value ?? '').trim().isEmpty ? null : value!.trim();
}

void showUndo(BuildContext context, String message, Future<void> Function() undo) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
    content: Text(message),
    action: SnackBarAction(label: 'Undo', onPressed: () => unawaited(undo())),
  ));
}

const priorityNames = ['None', 'Low', 'Medium', 'High'];
const priorityColors = [C.muted, C.blue, C.accent, C.red];

class PriorityDot extends StatelessWidget {
  const PriorityDot(this.priority, {super.key});
  final int priority;

  @override
  Widget build(BuildContext context) => Tooltip(
        message: '${priorityNames[priority.clamp(0, 3)]} priority',
        child: Container(
          width: 9,
          height: 9,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: priority > 0 ? priorityColors[priority.clamp(0, 3)] : Colors.transparent,
            border: Border.all(color: priorityColors[priority.clamp(0, 3)]),
          ),
        ),
      );
}

/// "Today 17:00", "Fri 23 Oct" — red when overdue.
class DueChip extends StatelessWidget {
  const DueChip(this.due, {super.key});
  final DateTime due;

  @override
  Widget build(BuildContext context) {
    final overdue = due.isBefore(DateTime.now());
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: overdue ? const Color(0xFF2A1A1A) : C.raised,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(shortTime(due), style: TextStyle(fontSize: 12, color: overdue ? C.red : C.text2)),
    );
  }
}

String shortTime(DateTime t) {
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final day = DateTime(t.year, t.month, t.day);
  final hm = '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
  final diff = day.difference(today).inDays;
  final d = diff == 0
      ? 'Today'
      : diff == 1
          ? 'Tomorrow'
          : '${days[t.weekday - 1]} ${t.day} ${months[t.month - 1]}';
  return '$d $hm';
}
