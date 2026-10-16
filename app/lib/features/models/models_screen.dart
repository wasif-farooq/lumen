import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/cards.dart';
import '../../core/format.dart';

/// Providers & models: which model does each job, the providers they come from, Ollama downloads.
class ModelsScreen extends StatefulWidget {
  const ModelsScreen({super.key, required this.state, this.embedded = false});
  final AppState state;
  final bool embedded; // inside the Settings tabs: no page title

  @override
  State<ModelsScreen> createState() => _ModelsScreenState();
}

const _roles = [
  ('agent', 'Chat agent', 'Answers your questions and runs searches. Needs tool calling.', Icons.chat_bubble_outline),
  ('vision', 'Images & video', 'Describes pictures, scans and video frames while indexing. Needs vision.', Icons.image_outlined),
];

/// Ready-made addresses for common OpenAI-compatible servers.
const _presets = [
  ('LM Studio', 'http://localhost:1234/v1', false),
  ('llama.cpp', 'http://localhost:8080/v1', false),
  ('vLLM', 'http://localhost:8000/v1', false),
  ('OpenAI', 'https://api.openai.com/v1', true),
  ('OpenRouter', 'https://openrouter.ai/api/v1', true),
];

class _ModelsScreenState extends State<ModelsScreen> {
  Map<String, dynamic>? data;
  String? error;
  final Map<String, Map<String, dynamic>> _tests = {}; // provider id -> {ok, message} or {busy}
  final Map<String, Map<String, dynamic>> _checks = {}; // role -> last compatibility check of its model
  Timer? _pullPoll;

  AppState get s => widget.state;
  List<Map<String, dynamic>> get _providers => [for (final p in (data?['providers'] as List? ?? [])) Map<String, dynamic>.from(p)];
  Map<String, dynamic> get _rolesNow => Map<String, dynamic>.from(data?['roles'] ?? {});
  List<Map<String, dynamic>> get _pulls => [for (final p in (data?['pulls'] as List? ?? [])) Map<String, dynamic>.from(p)];
  Map<String, dynamic>? _provider(String? id) => _providers.where((p) => p['id'] == id).firstOrNull;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _pullPoll?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final d = await s.api.providers();
      if (!mounted) return;
      setState(() {
        data = d;
        error = null;
      });
      // Keep polling while a model download runs
      final pulling = _pulls.any((p) => p['done'] != true);
      if (pulling && _pullPoll == null) {
        _pullPoll = Timer.periodic(const Duration(seconds: 1), (_) => _load());
      } else if (!pulling) {
        _pullPoll?.cancel();
        _pullPoll = null;
      }
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    }
  }

  void _toast(String msg) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _test(String id) async {
    setState(() => _tests[id] = {'busy': true});
    try {
      final r = await s.api.testProvider(id);
      if (mounted) setState(() => _tests[id] = r);
    } catch (e) {
      if (mounted) setState(() => _tests[id] = {'ok': false, 'message': '$e'});
    }
  }

  /// Pick provider + model for a role. Switching to a cloud provider asks first; then the model
  /// is tried on the job before it is used, and a failed check offers to pick another.
  Future<void> _chooseModel(String role, String title) async {
    final now = Map<String, dynamic>.from(_rolesNow[role] ?? {});
    String? pid = now['provider'], model = now['model'];
    while (true) {
      // Loops back to the picker when a failed check is answered with "Pick another"
      if (!mounted) return;
      final picked = await showDialog<(String, String)>(
        context: context,
        builder: (_) => _ModelPicker(api: s.api, title: title, providers: _providers, role: role, provider: pid, model: model),
      );
      if (picked == null) return;
      final (newPid, newModel) = picked;
      (pid, model) = (newPid, newModel);
      if (!await _confirmCloud(role, title, now, newPid)) return;
      if (!mounted) return;
      final choice = await showDialog<String>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _CheckDialog(api: s.api, role: role, title: title, provider: newPid, model: newModel, choosing: true,
            onResult: (r) => _checks[role] = r),
      );
      if (choice == 'use') return _useModel(role, title, newPid, newModel);
      if (choice != 'another') return;
    }
  }

  /// Re-run the check on the model a job uses now.
  Future<void> _checkCurrent(String role, String title) async {
    final now = Map<String, dynamic>.from(_rolesNow[role] ?? {});
    await showDialog<String>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _CheckDialog(api: s.api, role: role, title: title, provider: now['provider'], model: '${now['model']}',
          onResult: (r) => _checks[role] = r),
    );
    if (mounted) setState(() {});
  }

  Future<bool> _confirmCloud(String role, String title, Map<String, dynamic> now, String pid) async {
    final p = _provider(pid);
    final wasCloud = _provider(now['provider'])?['cloud'] == true;
    if (p?['cloud'] == true && !wasCloud && mounted) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (_) => AlertDialog(
          icon: const Icon(Icons.cloud_outlined, color: C.accent),
          title: Text('Use ${p!['name']} for ${title.toLowerCase()}?'),
          content: Text(
            role == 'vision'
                ? 'Your pictures, scanned documents and video frames will be sent to ${p['base_url']} while indexing. '
                    'They leave this laptop, and that service may log or keep them.'
                : 'Your questions and the contents of files the agent reads will be sent to ${p['base_url']}. '
                    'They leave this laptop, and that service may log or keep them.',
            style: const TextStyle(color: C.text3),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep it local')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Send to the cloud')),
          ],
        ),
      );
      return ok == true;
    }
    return true;
  }

  Future<void> _useModel(String role, String title, String pid, String model) async {
    try {
      await s.api.setRole(role, pid, model);
      await Future.wait([_load(), s.refreshStatus()]);
      _toast('$title now uses $model${role == 'vision' ? '. It applies from the next indexing run.' : ''}');
    } on ApiError catch (e) {
      _toast(e.message);
    }
  }

  Future<void> _setSpeech(String model) async {
    try {
      await s.api.setRole('speech', 'local', model);
      await Future.wait([_load(), s.refreshStatus()]);
      _toast('Speech uses whisper-$model from the next indexing run.');
    } on ApiError catch (e) {
      _toast(e.message);
    }
  }

  Future<void> _editProvider([Map<String, dynamic>? p]) async {
    final saved = await showDialog<Map<String, dynamic>>(context: context, builder: (_) => _ProviderDialog(api: s.api, provider: p));
    if (saved == null) return;
    await _load();
    _test(saved['id']);
  }

  Future<void> _removeProvider(Map<String, dynamic> p) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('Remove ${p['name']}?'),
        content: const Text('Its address and API key are deleted from this laptop.', style: TextStyle(color: C.text3)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Remove')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await s.api.deleteProvider(p['id']);
      await _load();
    } on ApiError catch (e) {
      _toast(e.message);
    }
  }

  Future<void> _pull(String model) async {
    if (model.trim().isEmpty) return;
    try {
      await s.api.pullModel(model.trim());
      await _load();
    } on ApiError catch (e) {
      _toast(e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final roles = _rolesNow;
    return ListView(
      padding: EdgeInsets.fromLTRB(32, widget.embedded ? 20 : 28, 32, 40),
      children: [
        if (!widget.embedded) const Text('Models', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
        const Text('Which model does each job, and where it runs.', style: TextStyle(color: C.text3)),
        if (error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(error!, style: const TextStyle(color: C.red))),
        const SizedBox(height: 24),
        SectionCard(
          title: 'What each job uses',
          child: Column(children: [
            for (final (id, title, desc, icon) in _roles)
              _RoleRow(
                icon: icon,
                title: title,
                desc: desc,
                model: '${roles[id]?['model'] ?? '–'}',
                provider: _provider(roles[id]?['provider']),
                onChange: data == null ? null : () => _chooseModel(id, title),
                onCheck: data == null ? null : () => _checkCurrent(id, title),
                check: _checks[id] != null && _checks[id]!['model'] == roles[id]?['model'] ? _checks[id] : null,
              ),
            _RoleRow(
              icon: Icons.graphic_eq,
              title: 'Speech',
              desc: 'Transcribes video and audio while indexing. Always runs on this laptop, on the CPU.',
              model: 'whisper-${roles['speech']?['model'] ?? 'small'}',
              local: true,
              trailing: PopupMenuButton<String>(
                tooltip: 'Speech model size',
                onSelected: _setSpeech,
                itemBuilder: (_) => [
                  for (final m in (data?['speech_models'] as List? ?? []).cast<String>())
                    PopupMenuItem(
                      value: m,
                      child: Row(children: [
                        Icon(m == roles['speech']?['model'] ? Icons.radio_button_checked : Icons.radio_button_off, size: 16, color: C.accent),
                        const SizedBox(width: 10),
                        Text('whisper-$m'),
                        const SizedBox(width: 8),
                        Text(switch (m) { 'tiny' || 'base' => 'fastest', 'small' => 'balanced', 'medium' => 'better', _ => 'best, slowest' },
                            style: const TextStyle(fontSize: 12, color: C.muted)),
                      ]),
                    ),
                ],
                child: const IgnorePointer(child: OutlinedButton(onPressed: _noop, child: Text('Change'))),
              ),
            ),
          ]),
        ),
        const SizedBox(height: 20),
        TwoColumns(children: [
          CardColumn(children: [
            SectionCard(
              title: 'Providers',
              trailing: OutlinedButton.icon(
                onPressed: () => _editProvider(),
                style: OutlinedButton.styleFrom(minimumSize: const Size(0, 36)),
                icon: const Icon(Icons.add, size: 16),
                label: const Text('Add provider'),
              ),
              child: Column(children: [
                for (final p in _providers)
                  _ProviderTile(
                    p: p,
                    test: _tests[p['id']],
                    onTest: () => _test(p['id']),
                    onEdit: () => _editProvider(p),
                    onRemove: p['builtin'] == true ? null : () => _removeProvider(p),
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
            _OllamaDownloads(pulls: _pulls, onPull: _pull),
          ]),
        ]),
      ],
    );
  }
}

void _noop() {}

class _Badge extends StatelessWidget {
  const _Badge({required this.cloud});
  final bool cloud;
  @override
  Widget build(BuildContext context) => Tooltip(
        message: cloud ? 'File contents and images are sent to this service' : 'Runs on this laptop or your local network',
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(color: (cloud ? C.accent : C.green).withValues(alpha: 0.12), borderRadius: BorderRadius.circular(20)),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(cloud ? Icons.cloud_outlined : Icons.lock_outline, size: 12, color: cloud ? C.accent : C.green),
            const SizedBox(width: 4),
            Text(cloud ? 'Cloud' : 'Local', style: TextStyle(fontSize: 12, color: cloud ? C.accent : C.green, fontWeight: FontWeight.w500)),
          ]),
        ),
      );
}

class _RoleRow extends StatelessWidget {
  const _RoleRow({required this.icon, required this.title, required this.desc, required this.model, this.provider, this.local = false, this.onChange, this.onCheck, this.check, this.trailing});
  final IconData icon;
  final String title, desc, model;
  final Map<String, dynamic>? provider;
  final bool local;
  final VoidCallback? onChange, onCheck;
  final Map<String, dynamic>? check; // last compatibility check of this model
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final cloud = provider?['cloud'] == true;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: C.surface2, borderRadius: BorderRadius.circular(12)),
      child: Row(children: [
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(color: C.raised, borderRadius: BorderRadius.circular(10)),
          child: Icon(icon, size: 20, color: C.text2),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
            Text(desc, style: const TextStyle(fontSize: 13, color: C.muted)),
            if (check != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Row(children: [
                  Icon(check!['ok'] == true ? Icons.verified_outlined : Icons.error_outline, size: 14, color: check!['ok'] == true ? C.green : C.red),
                  const SizedBox(width: 6),
                  Flexible(
                    child: Text(
                      check!['ok'] == true
                          ? 'Checked: works for this job'
                          : 'Check failed: ${(check!['checks'] as List).lastWhere((c) => c['ok'] != true, orElse: () => {'detail': ''})['detail']}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 12.5, color: check!['ok'] == true ? C.green : C.red),
                    ),
                  ),
                ]),
              ),
          ]),
        ),
        const SizedBox(width: 16),
        Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Text(model, style: monoStyle(size: 13, color: C.text)),
          const SizedBox(height: 4),
          Row(mainAxisSize: MainAxisSize.min, children: [
            Text(local ? 'This laptop' : '${provider?['name'] ?? '–'}', style: const TextStyle(fontSize: 12.5, color: C.text3)),
            const SizedBox(width: 8),
            _Badge(cloud: !local && cloud),
          ]),
        ]),
        const SizedBox(width: 16),
        if (onCheck != null) ...[
          TextButton(onPressed: onCheck, child: const Text('Check')),
          const SizedBox(width: 4),
        ],
        trailing ?? OutlinedButton(onPressed: onChange, child: const Text('Change')),
      ]),
    );
  }
}

class _ProviderTile extends StatelessWidget {
  const _ProviderTile({required this.p, required this.test, required this.onTest, required this.onEdit, this.onRemove});
  final Map<String, dynamic> p;
  final Map<String, dynamic>? test;
  final VoidCallback onTest, onEdit;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final used = (p['used_by'] as List? ?? []).map((r) => switch (r) { 'agent' => 'chat', 'vision' => 'images & video', _ => '$r' }).toList();
    final busy = test?['busy'] == true;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.fromLTRB(14, 12, 6, 12),
      decoration: BoxDecoration(color: C.surface2, borderRadius: BorderRadius.circular(12)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(p['kind'] == 'ollama' ? Icons.memory : Icons.hub_outlined, size: 18, color: C.text2),
          const SizedBox(width: 10),
          Flexible(child: Text('${p['name']}', style: const TextStyle(fontWeight: FontWeight.w600), overflow: TextOverflow.ellipsis)),
          const SizedBox(width: 8),
          _Badge(cloud: p['cloud'] == true),
          const Spacer(),
          TextButton(onPressed: busy ? null : onTest, child: Text(busy ? 'Testing…' : 'Test')),
          IconButton(tooltip: 'Edit ${p['name']}', onPressed: onEdit, icon: const Icon(Icons.edit_outlined, size: 16, color: C.text3)),
          if (onRemove != null) IconButton(tooltip: 'Remove ${p['name']}', onPressed: onRemove, icon: const Icon(Icons.delete_outline, size: 16, color: C.muted)),
        ]),
        const SizedBox(height: 2),
        Padding(
          padding: const EdgeInsets.only(left: 28),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${p['base_url']}', style: monoStyle(size: 12.5, color: C.text3)),
            const SizedBox(height: 2),
            Text(
              [
                p['kind'] == 'ollama' ? 'Ollama' : 'OpenAI-compatible',
                if (p['has_key'] == true) 'key ${p['key_hint']}',
                if (used.isNotEmpty) 'used for ${used.join(' and ')}',
              ].join(' · '),
              style: const TextStyle(fontSize: 12.5, color: C.muted),
            ),
            if (test != null && !busy)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Row(children: [
                  Icon(test!['ok'] == true ? Icons.check_circle_outline : Icons.error_outline, size: 15, color: test!['ok'] == true ? C.green : C.red),
                  const SizedBox(width: 6),
                  Expanded(child: Text('${test!['message']}', style: TextStyle(fontSize: 12.5, color: test!['ok'] == true ? C.green : C.red))),
                ]),
              ),
          ]),
        ),
      ]),
    );
  }
}

class _OllamaDownloads extends StatefulWidget {
  const _OllamaDownloads({required this.pulls, required this.onPull});
  final List<Map<String, dynamic>> pulls;
  final ValueChanged<String> onPull;
  @override
  State<_OllamaDownloads> createState() => _OllamaDownloadsState();
}

class _OllamaDownloadsState extends State<_OllamaDownloads> {
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
                        : (p['total'] ?? 0) > 0
                            ? '${humanSize(p['completed'] ?? 0)} of ${humanSize(p['total'])}'
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
                  value: p['done'] == true ? 1 : ((p['total'] ?? 0) > 0 ? (p['completed'] ?? 0) / p['total'] : null),
                  minHeight: 4,
                  color: p['done'] == true ? C.green : C.accent,
                  backgroundColor: C.raised,
                ),
              ),
          ],
        ]),
      );
}

/// Choose a provider, then one of its models (or type a name the list doesn't show).
class _ModelPicker extends StatefulWidget {
  const _ModelPicker({required this.api, required this.title, required this.providers, required this.role, this.provider, this.model});
  final Api api;
  final String title, role;
  final List<Map<String, dynamic>> providers;
  final String? provider, model;
  @override
  State<_ModelPicker> createState() => _ModelPickerState();
}

class _ModelPickerState extends State<_ModelPicker> {
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
    _fetch();
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
    } catch (e) {
      if (mounted) setState(() => error = '$e');
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
                  child: Row(children: [Text('${p['name']}'), const SizedBox(width: 8), _Badge(cloud: p['cloud'] == true)]),
                ),
            ],
            onChanged: (v) {
              if (v == null || v == pid) return;
              setState(() {
                pid = v;
                model = null;
              });
              _fetch();
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

/// Add or edit a provider. Presets fill in the address of common servers.
class _ProviderDialog extends StatefulWidget {
  const _ProviderDialog({required this.api, this.provider});
  final Api api;
  final Map<String, dynamic>? provider;
  @override
  State<_ProviderDialog> createState() => _ProviderDialogState();
}

class _ProviderDialogState extends State<_ProviderDialog> {
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
    } on ApiError catch (e) {
      setState(() => error = e.message);
    } catch (e) {
      setState(() => error = '$e');
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

/// Tries a model on a job and shows what passed. While choosing: "Use this model" when it works,
/// "Pick another" or "Use anyway" when it doesn't. Pops 'use', 'another' or null.
class _CheckDialog extends StatefulWidget {
  const _CheckDialog({required this.api, required this.role, required this.title, required this.provider, required this.model, this.choosing = false, this.onResult});
  final Api api;
  final String role, title, provider, model;
  final bool choosing;
  final ValueChanged<Map<String, dynamic>>? onResult;
  @override
  State<_CheckDialog> createState() => _CheckDialogState();
}

class _CheckDialogState extends State<_CheckDialog> {
  Map<String, dynamic>? result;
  String? error;

  @override
  void initState() {
    super.initState();
    _run();
  }

  Future<void> _run() async {
    try {
      final r = {...await widget.api.checkModel(widget.role, widget.provider, widget.model), 'model': widget.model};
      widget.onResult?.call(r);
      if (mounted) setState(() => result = r);
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = result;
    final ok = r?['ok'] == true;
    final job = widget.role == 'agent' ? 'chat' : 'images & video';
    return AlertDialog(
      icon: r == null && error == null
          ? const SizedBox(width: 28, height: 28, child: CircularProgressIndicator(strokeWidth: 3, color: C.accent))
          : Icon(ok ? Icons.verified_outlined : Icons.error_outline, color: ok ? C.green : C.red, size: 30),
      title: Text(r == null && error == null
          ? 'Checking ${widget.model}…'
          : ok
              ? '${widget.model} works for $job'
              : '${widget.model} may not work for $job'),
      content: SizedBox(
        width: 460,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (r == null && error == null)
            Text(
              widget.role == 'agent'
                  ? 'Asking it to search your files, to see that it calls tools. A local model may take a minute to load.'
                  : 'Showing it a test picture, to see that it reads images. A local model may take a minute to load.',
              style: const TextStyle(color: C.text3),
            ),
          if (error != null) Text(error!, style: const TextStyle(color: C.red)),
          if (r != null) ...[
            for (final c in (r['checks'] as List))
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(c['ok'] == true ? Icons.check_circle : Icons.cancel, size: 18, color: c['ok'] == true ? C.green : C.red),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${c['name']}', style: const TextStyle(fontWeight: FontWeight.w500)),
                      Text('${c['detail']}', style: const TextStyle(fontSize: 13, color: C.text3)),
                    ]),
                  ),
                ]),
              ),
            Text('Took ${r['seconds']} s', style: const TextStyle(fontSize: 12.5, color: C.muted)),
          ],
        ]),
      ),
      actions: [
        if (r == null && error == null)
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel'))
        else if (!widget.choosing)
          FilledButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))
        else if (ok)
          FilledButton(onPressed: () => Navigator.pop(context, 'use'), child: const Text('Use this model'))
        else ...[
          TextButton(onPressed: () => Navigator.pop(context, 'use'), child: const Text('Use anyway')),
          FilledButton(onPressed: () => Navigator.pop(context, 'another'), child: const Text('Pick another')),
        ],
      ],
    );
  }
}
