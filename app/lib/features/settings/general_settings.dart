import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../core/errors/run_guarded.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/cards.dart';
import '../../shared/widgets/error_views.dart';
import 'diagnostics_card.dart';
import 'general_controller.dart';
import 'notes_settings.dart';
import 'phones_card.dart';
import 'setting_controls.dart';

/// General settings: what gets indexed, power use, paired phones and help with problems.
class GeneralSettings extends StatefulWidget {
  const GeneralSettings({super.key, required this.state});
  final AppState state;

  @override
  State<GeneralSettings> createState() => _GeneralSettingsState();
}

class _GeneralSettingsState extends State<GeneralSettings> {
  late final c = GeneralController(widget.state)..load();

  @override
  void dispose() {
    c.dispose();
    super.dispose();
  }

  Future<void> _set(String key, Object value) => runGuarded(context, () => c.set(key, value), failure: 'Could not save');

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: Listenable.merge([widget.state, c]),
        builder: (context, _) {
          final st = widget.state.status ?? {};
          return ListView(
            padding: const EdgeInsets.fromLTRB(32, 20, 32, 40),
            children: [
              const Text('Saved as you change them. New indexing settings apply from the next run.', style: TextStyle(color: C.text3)),
              if (c.loadError != null)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: ErrorCard(error: c.loadError!, title: "Couldn't load the settings", onRetry: c.load),
                ),
              const SizedBox(height: 24),
              TwoColumns(children: [
                CardColumn(children: [
                  _IndexingCard(settings: c.settings, onSet: _set),
                  _PowerCard(settings: c.settings, power: Map<String, dynamic>.from(st['power'] as Map? ?? const {}), onSet: _set),
                  NotesSettingsCard(settings: c.settings, onSet: _set),
                ]),
                CardColumn(children: [
                  PhonesCard(c: c, lan: st['lan'] == true),
                  DiagnosticsCard(c: c),
                ]),
              ]),
            ],
          );
        },
      );
}

class _IndexingCard extends StatelessWidget {
  const _IndexingCard({required this.settings, required this.onSet});
  final Map<String, dynamic>? settings;
  final Future<void> Function(String key, Object value) onSet;

  bool _on(String key) => settings?[key] as bool? ?? true;

  @override
  Widget build(BuildContext context) => SectionCard(
        title: 'What gets indexed',
        child: Column(children: [
          const SettingToggle(title: 'Document text', subtitle: 'PDF, Word, text and code. Cheap, runs on battery too.', value: true),
          SettingToggle(title: 'Describe images and scans', subtitle: 'The vision model writes what each picture shows.', value: _on('captions'), onChanged: (v) => onSet('captions', v)),
          SettingToggle(title: 'Describe videos', subtitle: 'Six frames per video, one description.', value: _on('media'), onChanged: (v) => onSet('media', v)),
          SettingToggle(title: 'Transcribe speech', subtitle: 'Whisper on the CPU, with timestamps.', value: _on('transcripts'), onChanged: (v) => onSet('transcripts', v)),
        ]),
      );
}

class _PowerCard extends StatelessWidget {
  const _PowerCard({required this.settings, required this.power, required this.onSet});
  final Map<String, dynamic>? settings;
  final Map<String, dynamic> power;
  final Future<void> Function(String key, Object value) onSet;

  static const _modes = [
    ('auto', 'Auto', 'AI work only when plugged in. Unplug and it pauses after the current file.'),
    ('saver', 'Saver', 'Files and document text only. No models.'),
    ('performance', 'Performance', 'Everything, all cores, even on battery.'),
  ];

  @override
  Widget build(BuildContext context) {
    final ac = power['on_ac'] == true;
    return SectionCard(
      title: 'Power',
      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(ac ? Icons.power_outlined : Icons.battery_std_outlined, size: 16, color: ac ? C.green : C.accent),
        const SizedBox(width: 6),
        Text('${ac ? 'Plugged in' : 'On battery'}${power['battery'] != null ? ' · ${power['battery']}%' : ''}',
            style: TextStyle(fontSize: 13, color: ac ? C.green : C.accent)),
      ]),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Indexing mode', style: TextStyle(fontSize: 13, color: C.muted)),
        const SizedBox(height: 8),
        for (final (id, name, desc) in _modes)
          ModeOption(name: name, desc: desc, selected: (settings?['power_mode'] ?? 'auto') == id, onTap: () => onSet('power_mode', id)),
        if (power['ai_allowed'] == false && '${power['reason'] ?? ''}'.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4, bottom: 8),
            child: Text('AI work paused: ${power['reason']}', style: const TextStyle(fontSize: 13, color: C.accent)),
          ),
        SettingToggle(
          title: 'Run models on CPU only',
          subtitle: 'Keeps the GPU free. Chat was about 15× slower in our benchmark.',
          value: settings?['cpu_only'] as bool? ?? false,
          onChanged: (v) => onSet('cpu_only', v),
        ),
        Row(children: [
          const Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('CPU threads for indexing'),
              Text('Fewer threads, cooler laptop.', style: TextStyle(fontSize: 13, color: C.muted)),
            ]),
          ),
          NumberStepper(value: (settings?['threads'] as num? ?? 4).toInt(), onChanged: (v) => onSet('threads', v)),
        ]),
      ]),
    );
  }
}
