import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../core/models/json.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/cards.dart';

/// Download an Ollama model by name, with progress for running downloads.
class OllamaDownloads extends StatefulWidget {
  const OllamaDownloads({super.key, required this.pulls, required this.onPull});
  final List<Map<String, dynamic>> pulls;
  final ValueChanged<String> onPull;
  @override
  State<OllamaDownloads> createState() => _OllamaDownloadsState();
}

class _OllamaDownloadsState extends State<OllamaDownloads> {
  final _ctrl = TextEditingController();

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _submit() {
    widget.onPull(_ctrl.text);
    _ctrl.clear();
  }

  @override
  Widget build(BuildContext context) => SectionCard(
        title: 'Download an Ollama model',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Names from ollama.com/library, e.g. qwen2.5vl:3b for images or qwen3.5:2b for chat.', style: TextStyle(fontSize: 13, color: C.muted)),
          const SizedBox(height: 10),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _ctrl,
                style: monoStyle(size: 13, color: C.text),
                decoration: const InputDecoration(hintText: 'model:tag', isDense: true, border: OutlineInputBorder()),
                onSubmitted: (_) => _submit(),
              ),
            ),
            const SizedBox(width: 8),
            FilledButton.icon(onPressed: _submit, icon: const Icon(Icons.download, size: 16), label: const Text('Download')),
          ]),
          for (final p in widget.pulls.reversed) ...[
            const SizedBox(height: 12),
            Row(children: [
              Expanded(child: Text('${p['model']}', style: monoStyle(size: 13, color: C.text))),
              Text(
                p['error'] != null
                    ? 'Failed'
                    : p['done'] == true
                        ? 'Ready'
                        : numOf(p['total']) > 0
                            ? '${humanSize(numOf(p['completed']).toInt())} of ${humanSize(numOf(p['total']).toInt())}'
                            : '${p['status']}',
                style: TextStyle(fontSize: 12.5, color: p['error'] != null ? C.red : (p['done'] == true ? C.green : C.text3)),
              ),
            ]),
            const SizedBox(height: 6),
            if (p['error'] != null)
              Text('${p['error']}', style: const TextStyle(fontSize: 12.5, color: C.red))
            else
              ClipRRect(
                borderRadius: BorderRadius.circular(3),
                child: LinearProgressIndicator(
                  value: p['done'] == true ? 1 : (numOf(p['total']) > 0 ? numOf(p['completed']) / numOf(p['total']) : null),
                  minHeight: 4,
                  color: p['done'] == true ? C.green : C.accent,
                  backgroundColor: C.raised,
                ),
              ),
          ],
        ]),
      );
}
