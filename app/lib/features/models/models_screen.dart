import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/cards.dart';
import '../../shared/widgets/error_views.dart';
import 'models_actions.dart';
import 'models_controller.dart';
import 'ollama_downloads.dart';
import 'provider_tile.dart';
import 'role_row.dart';

/// Providers & models: which model does each job, the providers they come from, Ollama downloads.
class ModelsScreen extends StatefulWidget {
  const ModelsScreen({super.key, required this.state, this.embedded = false});
  final AppState state;
  final bool embedded; // inside the Settings tabs: no page title

  @override
  State<ModelsScreen> createState() => _ModelsScreenState();
}

const _jobs = [
  ('agent', 'Chat agent', 'Answers your questions and runs searches. Needs tool calling.', Icons.chat_bubble_outline),
  ('vision', 'Images & video', 'Describes pictures, scans and video frames while indexing. Needs vision.', Icons.image_outlined),
];

class _ModelsScreenState extends State<ModelsScreen> {
  late final c = ModelsController(widget.state)..load();

  @override
  void dispose() {
    c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final actions = ModelsActions(context, c);
    return ListenableBuilder(
      listenable: c,
      builder: (context, _) => ListView(
        padding: EdgeInsets.fromLTRB(32, widget.embedded ? 20 : 28, 32, 40),
        children: [
          if (!widget.embedded) const Text('Models', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
          const Text('Which model does each job, and where it runs.', style: TextStyle(color: C.text3)),
          if (c.loadError != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: ErrorCard(error: c.loadError!, title: "Couldn't load the models", onRetry: c.load),
            ),
          const SizedBox(height: 24),
          SectionCard(
            title: 'What each job uses',
            child: Column(children: [
              for (final (id, title, desc, icon) in _jobs)
                RoleRow(
                  icon: icon,
                  title: title,
                  desc: desc,
                  model: '${c.role(id)['model'] ?? '–'}',
                  provider: c.provider(c.role(id)['provider']),
                  onChange: c.data == null ? null : () => actions.chooseModel(id, title),
                  onCheck: c.data == null ? null : () => actions.checkCurrent(id, title),
                  check: c.checkOf(id),
                ),
              RoleRow(
                icon: Icons.graphic_eq,
                title: 'Speech',
                desc: 'Transcribes video and audio while indexing. Always runs on this laptop, on the CPU.',
                model: 'whisper-${c.role('speech')['model'] ?? 'small'}',
                local: true,
                trailing: _SpeechMenu(models: c.speechModels, current: c.role('speech')['model'], onPick: actions.setSpeech),
              ),
            ]),
          ),
          const SizedBox(height: 20),
          TwoColumns(children: [
            CardColumn(children: [
              SectionCard(
                title: 'Providers',
                trailing: OutlinedButton.icon(
                  onPressed: actions.editProvider,
                  style: OutlinedButton.styleFrom(minimumSize: const Size(0, 36)),
                  icon: const Icon(Icons.add, size: 16),
                  label: const Text('Add provider'),
                ),
                child: Column(children: [
                  for (final p in c.providers)
                    ProviderTile(
                      p: p,
                      test: c.tests[p['id']],
                      onTest: () => c.test(p['id'] as String),
                      onEdit: () => actions.editProvider(p),
                      onRemove: p['builtin'] == true ? null : () => actions.removeProvider(p),
                    ),
                  const Align(
                    alignment: Alignment.centerLeft,
                    child: Text('Any server with an OpenAI-compatible API works: LM Studio, llama.cpp, vLLM, OpenAI, OpenRouter…',
                        style: TextStyle(fontSize: 13, color: C.muted)),
                  ),
                ]),
              ),
            ]),
            CardColumn(children: [
              OllamaDownloads(pulls: c.pulls, onPull: actions.pull),
            ]),
          ]),
        ],
      ),
    );
  }
}

/// Whisper sizes, from fastest to best.
class _SpeechMenu extends StatelessWidget {
  const _SpeechMenu({required this.models, required this.current, required this.onPick});
  final List<String> models;
  final Object? current;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) => PopupMenuButton<String>(
        tooltip: 'Speech model size',
        onSelected: onPick,
        itemBuilder: (_) => [
          for (final m in models)
            PopupMenuItem(
              value: m,
              child: Row(children: [
                Icon(m == current ? Icons.radio_button_checked : Icons.radio_button_off, size: 16, color: C.accent),
                const SizedBox(width: 10),
                Text('whisper-$m'),
                const SizedBox(width: 8),
                Text(switch (m) { 'tiny' || 'base' => 'fastest', 'small' => 'balanced', 'medium' => 'better', _ => 'best, slowest' },
                    style: const TextStyle(fontSize: 12, color: C.muted)),
              ]),
            ),
        ],
        child: const IgnorePointer(child: OutlinedButton(onPressed: _noop, child: Text('Change'))),
      );
}

void _noop() {}
