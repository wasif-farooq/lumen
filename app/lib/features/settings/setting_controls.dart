import 'package:flutter/material.dart';

import '../../shared/theme.dart';

/// A setting with a switch.
class SettingToggle extends StatelessWidget {
  const SettingToggle({super.key, required this.title, required this.subtitle, required this.value, this.onChanged});
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

/// One choice of several (power mode).
class ModeOption extends StatelessWidget {
  const ModeOption({super.key, required this.name, required this.desc, required this.selected, required this.onTap});
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

/// − n + for a small number (threads).
class NumberStepper extends StatelessWidget {
  const NumberStepper({super.key, required this.value, required this.onChanged});
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
