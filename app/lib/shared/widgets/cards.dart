import 'package:flutter/material.dart';

import '../theme.dart';

/// Side by side on wide windows, stacked on narrow ones.
class TwoColumns extends StatelessWidget {
  const TwoColumns({super.key, required this.children});
  final List<Widget> children;
  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, c) => c.maxWidth >= 900
            ? Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                for (final (i, child) in children.indexed) ...[if (i > 0) const SizedBox(width: 20), Expanded(child: child)],
              ])
            : Column(children: children),
      );
}

class CardColumn extends StatelessWidget {
  const CardColumn({super.key, required this.children});
  final List<Widget> children;
  @override
  Widget build(BuildContext context) =>
      Column(children: [for (final c in children) Padding(padding: const EdgeInsets.only(bottom: 20), child: c)]);
}

/// A titled panel, optionally with an action on the right of the title.
class SectionCard extends StatelessWidget {
  const SectionCard({super.key, required this.title, required this.child, this.trailing});
  final String title;
  final Widget child;
  final Widget? trailing;
  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(color: C.surface, borderRadius: BorderRadius.circular(14), border: Border.all(color: C.line)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600))),
            ?trailing,
          ]),
          const SizedBox(height: 14),
          child,
        ]),
      );
}
