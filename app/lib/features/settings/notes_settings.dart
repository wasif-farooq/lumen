import 'package:flutter/material.dart';

import '../../shared/theme.dart';
import '../../shared/widgets/cards.dart';
import 'setting_controls.dart';

/// Settings → General: where notes are saved, and how reminders reach you.
class NotesSettingsCard extends StatelessWidget {
  const NotesSettingsCard({super.key, required this.settings, required this.onSet});
  final Map<String, dynamic>? settings;
  final Future<void> Function(String key, Object value) onSet;

  bool _on(String key) => settings?[key] as bool? ?? true;

  @override
  Widget build(BuildContext context) => SectionCard(
        title: 'Notes & reminders',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Notes are saved as Markdown files in', style: TextStyle(fontSize: 13, color: C.muted)),
          const SizedBox(height: 4),
          SelectableText('${settings?['notes_folder'] ?? '…'}', style: monoStyle(size: 12.5, color: C.text2)),
          const SizedBox(height: 12),
          SettingToggle(
            title: 'Desktop notifications',
            subtitle: 'A notification on the laptop when a reminder goes off, even with the app closed.',
            value: _on('reminder_notify'),
            onChanged: (v) => onSet('reminder_notify', v),
          ),
          SettingToggle(
            title: 'Say reminders out loud',
            subtitle: 'While voice chat is on, Lumen says the reminder.',
            value: _on('reminder_speak'),
            onChanged: (v) => onSet('reminder_speak', v),
          ),
        ]),
      );
}
