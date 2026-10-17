import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../core/errors/run_guarded.dart';
import '../../shared/theme.dart';
import 'planner_controller.dart';
import 'planner_parts.dart';

/// To-dos: the lists, and the open list's to-dos (tick, priority, drag to reorder, quick add).
class TodosTab extends StatelessWidget {
  const TodosTab({super.key, required this.c, this.compact = false});
  final PlannerController c;
  final bool compact;

  Future<void> _newList(BuildContext context) async {
    final name = await askText(context, 'New list', 'Name, e.g. Shopping');
    if (name != null && context.mounted) await runGuarded(context, () => c.newList(name), failure: 'Could not make the list');
  }

  @override
  Widget build(BuildContext context) {
    final lists = compact
        ? SizedBox(
            height: 48,
            child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: 12), children: [
              for (final l in c.lists)
                Padding(
                  padding: const EdgeInsets.only(right: 8, top: 8),
                  child: ChoiceChip(
                    label: Text('${l.name} ${l.open}'),
                    selected: l.id == c.listId,
                    onSelected: (_) => unawaited(c.showList(l.id)),
                  ),
                ),
              IconButton(tooltip: 'New list', onPressed: () => _newList(context), icon: const Icon(Icons.add)),
            ]),
          )
        : SizedBox(
            width: 220,
            child: ListView(padding: const EdgeInsets.all(12), children: [
              for (final l in c.lists)
                ListTile(
                  dense: true,
                  selected: l.id == c.listId,
                  selectedTileColor: C.raised,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  leading: const Icon(Icons.list, size: 18),
                  title: Text(l.name),
                  trailing: Text('${l.open}', style: const TextStyle(color: C.muted)),
                  onTap: () => unawaited(c.showList(l.id)),
                ),
              TextButton.icon(onPressed: () => _newList(context), icon: const Icon(Icons.add, size: 18), label: const Text('New list')),
            ]),
          );
    final items = _Items(c: c);
    return compact
        ? Column(children: [lists, Expanded(child: items)])
        : Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            lists,
            const VerticalDivider(width: 1, color: C.line),
            Expanded(child: items),
          ]);
  }
}

class _Items extends StatefulWidget {
  const _Items({required this.c});
  final PlannerController c;

  @override
  State<_Items> createState() => _ItemsState();
}

class _ItemsState extends State<_Items> {
  final _add = TextEditingController();
  final _due = TextEditingController();
  bool showDone = false;

  @override
  void dispose() {
    _add.dispose();
    _due.dispose();
    super.dispose();
  }

  Future<void> _addTodo() async {
    final text = _add.text.trim();
    if (text.isEmpty) return;
    final due = _due.text.trim();
    await runGuarded(context, () => widget.c.addTodo(text, due: due.isEmpty ? null : due), failure: 'Could not add the to-do');
    _add.clear();
    _due.clear();
  }

  Widget _row(Todo t) => ListTile(
        key: ValueKey(t.id),
        leading: Checkbox(value: t.isDone, onChanged: (v) => runGuarded(context, () => widget.c.setDone(t, v ?? false), failure: 'Could not change it')),
        title: Text(t.text,
            style: TextStyle(decoration: t.isDone ? TextDecoration.lineThrough : null, color: t.isDone ? C.muted : C.text)),
        subtitle: t.due != null && !t.isDone ? Align(alignment: Alignment.centerLeft, child: DueChip(t.due!)) : null,
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          PopupMenuButton<int>(
            tooltip: 'Priority',
            onSelected: (p) => runGuarded(context, () => widget.c.setPriority(t, p), failure: 'Could not change it'),
            itemBuilder: (_) => [for (final (i, n) in priorityNames.indexed) PopupMenuItem(value: i, child: Text(n))],
            child: Padding(padding: const EdgeInsets.all(8), child: PriorityDot(t.priority)),
          ),
          IconButton(
            tooltip: 'Delete',
            onPressed: () => runGuarded(context, () => widget.c.deleteTodo(t), failure: 'Could not delete it'),
            icon: const Icon(Icons.close, size: 18, color: C.muted),
          ),
        ]),
      );

  @override
  Widget build(BuildContext context) {
    final c = widget.c;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
        child: LayoutBuilder(builder: (context, box) {
          final add = TextField(
            controller: _add,
            onSubmitted: (_) => _addTodo(),
            decoration: InputDecoration(hintText: 'Add to ${c.list?.name ?? 'the list'}…', isDense: true),
          );
          final due = TextField(
            controller: _due,
            onSubmitted: (_) => _addTodo(),
            decoration: const InputDecoration(hintText: 'Due (e.g. Friday 5pm)', isDense: true),
          );
          final button = IconButton(tooltip: 'Add', onPressed: _addTodo, icon: const Icon(Icons.add_task));
          if (box.maxWidth < 520) {
            return Column(children: [add, Row(children: [Expanded(child: due), button])]);
          }
          return Row(children: [Expanded(flex: 3, child: add), const SizedBox(width: 8), Expanded(child: due), button]);
        }),
      ),
      Expanded(
        child: c.todos.isEmpty && (!showDone || c.done.isEmpty)
            ? const Empty(icon: Icons.checklist, text: 'Nothing to do here. Add something above, or say “add … to my list” in chat.')
            : ListView(children: [
                ReorderableListView(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  buildDefaultDragHandles: true,
                  onReorderItem: (a, b) => unawaited(c.reorder(a, b)),
                  children: [for (final t in c.todos) _row(t)],
                ),
                if (c.done.isNotEmpty)
                  TextButton(
                    onPressed: () => setState(() => showDone = !showDone),
                    child: Text(showDone ? 'Hide done' : 'Show ${c.done.length} done'),
                  ),
                if (showDone) for (final t in c.done) _row(t),
              ]),
      ),
    ]);
  }
}
