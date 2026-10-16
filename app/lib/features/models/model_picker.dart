import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api.dart';
import '../../core/format.dart';
import '../../shared/theme.dart';
import 'provider_badge.dart';
import '../../core/errors/errors.dart';

/// Choose a provider, then one of its models (or type a name the list doesn't show).
class ModelPicker extends StatefulWidget {
  const ModelPicker({super.key, required this.api, required this.title, required this.providers, required this.role, this.provider, this.model});
  final Api api;
  final String title, role;
  final List<Map<String, dynamic>> providers;
  final String? provider, model;
  @override
  State<ModelPicker> createState() => _ModelPickerState();
}

class _ModelPickerState extends State<ModelPicker> {
  late String pid = widget.provider ?? widget.providers.first['id'];
  String? model;
  List<Map<String, dynamic>>? models;
  String? error;
  String filter = '';
  final _custom = TextEditingController();

  @override
  void initState() {
    super.initState();
    model = widget.model;
    unawaited(_fetch());
  }

  @override
  void dispose() {
    _custom.dispose();
    super.dispose();
  }

  Future<void> _fetch() async {
    setState(() {
      models = null;
      error = null;
    });
    try {
      final list = await widget.api.providerModels(pid);
      if (mounted) setState(() => models = [for (final m in list) Map<String, dynamic>.from(m)]);
    } on Object catch (e, st) {
      logUnexpected('list models', e, st);
      if (mounted) setState(() => error = userMessage(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    final shown = (models ?? []).where((m) => filter.isEmpty || '${m['id']}'.toLowerCase().contains(filter.toLowerCase())).toList();
    final picked = model ?? '';
    return AlertDialog(
      title: Text('Model for ${widget.title.toLowerCase()}'),
      content: SizedBox(
        width: 520,
        height: 440,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          DropdownButtonFormField<String>(
            initialValue: pid,
            decoration: const InputDecoration(labelText: 'Provider', border: OutlineInputBorder(), isDense: true),
            items: [
              for (final p in widget.providers)
                DropdownMenuItem(
                  value: p['id'] as String,
                  child: Row(children: [Text('${p['name']}'), const SizedBox(width: 8), ProviderBadge(cloud: p['cloud'] == true)]),
                ),
            ],
            onChanged: (v) {
              if (v == null || v == pid) return;
              setState(() {
                pid = v;
                model = null;
              });
              unawaited(_fetch());
            },
          ),
          const SizedBox(height: 12),
          TextField(
            decoration: const InputDecoration(hintText: 'Filter models', prefixIcon: Icon(Icons.search, size: 18), isDense: true, border: OutlineInputBorder()),
            onChanged: (v) => setState(() => filter = v),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: error != null
                ? Center(child: Text(error!, textAlign: TextAlign.center, style: const TextStyle(color: C.red)))
                : models == null
                    ? const Center(child: CircularProgressIndicator(color: C.accent))
                    : shown.isEmpty
                        ? const Center(child: Text('No models', style: TextStyle(color: C.muted)))
                        : ListView(children: [
                            for (final m in shown)
                              _ModelOption(m: m, role: widget.role, selected: m['id'] == picked, onTap: () => setState(() => model = m['id'])),
                          ]),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _custom,
            style: monoStyle(size: 13, color: C.text),
            decoration: const InputDecoration(hintText: 'Or type a model name', isDense: true, border: OutlineInputBorder()),
            onChanged: (v) => setState(() => model = v.trim().isEmpty ? null : v.trim()),
          ),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: picked.isEmpty ? null : () => Navigator.pop(context, (pid, picked)), child: const Text('Use this model')),
      ],
    );
  }
}

class _ModelOption extends StatelessWidget {
  const _ModelOption({required this.m, required this.role, required this.selected, required this.onTap});
  final Map<String, dynamic> m;
  final String role;
  final bool selected;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    // Known not to fit the job (Ollama reports what each model can do)
    final unfit = role == 'vision' && m['vision'] == false
        ? 'no vision'
        : (role == 'agent' && m['tools'] == false ? 'no tool calling' : null);
    final noVision = unfit != null;
    return Material(
      color: selected ? C.accentSoft : Colors.transparent,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: noVision ? null : onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
          child: Row(children: [
            Icon(selected ? Icons.radio_button_checked : Icons.radio_button_off, size: 16, color: noVision ? C.line2 : (selected ? C.accent : C.muted)),
            const SizedBox(width: 10),
            Expanded(child: Text('${m['id']}', style: monoStyle(size: 13, color: noVision ? C.muted : C.text), overflow: TextOverflow.ellipsis)),
            if (m['vision'] == true)
              const Padding(padding: EdgeInsets.only(left: 8), child: Icon(Icons.visibility_outlined, size: 15, color: C.blue)),
            if (role == 'agent' && m['tools'] == true)
              const Padding(padding: EdgeInsets.only(left: 8), child: Tooltip(message: 'Calls tools', child: Icon(Icons.build_outlined, size: 14, color: C.blue))),
            if (unfit != null) Text(unfit, style: const TextStyle(fontSize: 12, color: C.muted)),
            if (m['size'] != null) Padding(padding: const EdgeInsets.only(left: 10), child: Text(humanSize(m['size']), style: const TextStyle(fontSize: 12, color: C.muted))),
          ]),
        ),
      ),
    );
  }
}
