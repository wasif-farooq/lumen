import 'package:flutter/material.dart';

import '../../core/api/api.dart';
import '../../shared/theme.dart';
import '../../core/errors/errors.dart';

/// Ready-made addresses for common OpenAI-compatible servers.
const _presets = [
  ('LM Studio', 'http://localhost:1234/v1', false),
  ('llama.cpp', 'http://localhost:8080/v1', false),
  ('vLLM', 'http://localhost:8000/v1', false),
  ('OpenAI', 'https://api.openai.com/v1', true),
  ('OpenRouter', 'https://openrouter.ai/api/v1', true),
];

/// Add or edit a provider. Presets fill in the address of common servers.
class ProviderDialog extends StatefulWidget {
  const ProviderDialog({super.key, required this.api, this.provider});
  final Api api;
  final Map<String, dynamic>? provider;
  @override
  State<ProviderDialog> createState() => _ProviderDialogState();
}

class _ProviderDialogState extends State<ProviderDialog> {
  late final _name = TextEditingController(text: widget.provider?['name'] ?? '');
  late final _url = TextEditingController(text: widget.provider?['base_url'] ?? '');
  final _key = TextEditingController();
  bool _saving = false, _clearKey = false;
  String? error;

  bool get _editing => widget.provider != null;
  bool get _ollama => widget.provider?['kind'] == 'ollama';

  @override
  void dispose() {
    _name.dispose();
    _url.dispose();
    _key.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      error = null;
    });
    try {
      final saved = await widget.api.saveProvider({
        if (_editing) 'id': widget.provider!['id'],
        'kind': _ollama ? 'ollama' : 'openai',
        'name': _name.text.trim(),
        'base_url': _url.text.trim(),
        if (_key.text.trim().isNotEmpty) 'api_key': _key.text.trim(),
        if (_clearKey) 'clear_key': true,
      });
      if (mounted) Navigator.pop(context, saved);
    } on Object catch (e, st) {
      logUnexpected('save provider', e, st);
      if (mounted) setState(() => error = userMessage(e));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(_editing ? 'Edit ${widget.provider!['name']}' : 'Add a provider'),
        content: SizedBox(
          width: 480,
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (!_editing) ...[
              const Text('OpenAI-compatible server', style: TextStyle(fontSize: 13, color: C.muted)),
              const SizedBox(height: 8),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final (name, url, cloud) in _presets)
                  ActionChip(
                    avatar: Icon(cloud ? Icons.cloud_outlined : Icons.computer, size: 15),
                    label: Text(name),
                    onPressed: () => setState(() {
                      _name.text = name;
                      _url.text = url;
                    }),
                  ),
              ]),
              const SizedBox(height: 16),
            ],
            if (!_ollama) ...[
              TextField(controller: _name, decoration: const InputDecoration(labelText: 'Name', border: OutlineInputBorder(), isDense: true)),
              const SizedBox(height: 12),
            ],
            TextField(
              controller: _url,
              style: monoStyle(size: 13, color: C.text),
              decoration: InputDecoration(
                labelText: 'Address',
                hintText: _ollama ? 'http://127.0.0.1:11434' : 'http://localhost:1234/v1',
                border: const OutlineInputBorder(),
                isDense: true,
              ),
            ),
            if (!_ollama) ...[
              const SizedBox(height: 12),
              TextField(
                controller: _key,
                obscureText: true,
                decoration: InputDecoration(
                  labelText: 'API key',
                  hintText: widget.provider?['has_key'] == true ? 'Saved (${widget.provider!['key_hint']}). Type to replace' : 'Not needed for most local servers',
                  border: const OutlineInputBorder(),
                  isDense: true,
                ),
              ),
              if (widget.provider?['has_key'] == true)
                CheckboxListTile(
                  value: _clearKey,
                  onChanged: (v) => setState(() => _clearKey = v ?? false),
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  controlAffinity: ListTileControlAffinity.leading,
                  title: const Text('Remove the saved key'),
                ),
              const SizedBox(height: 8),
              const Text('The key is stored only on this laptop, readable by your user account.', style: TextStyle(fontSize: 12.5, color: C.muted)),
            ],
            if (error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(error!, style: const TextStyle(color: C.red))),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(onPressed: _saving ? null : _save, child: Text(_saving ? 'Saving…' : 'Save')),
        ],
      );
}
