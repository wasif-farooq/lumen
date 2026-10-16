import 'package:flutter/material.dart';

import '../../core/errors/run_guarded.dart';
import '../../shared/theme.dart';
import 'check_dialog.dart';
import 'model_picker.dart';
import 'models_controller.dart';
import 'provider_dialog.dart';

/// What the Models tab's buttons do: pick and check models, ask before anything goes to the
/// cloud, edit providers, download Ollama models.
class ModelsActions {
  ModelsActions(this.context, this.c);
  final BuildContext context;
  final ModelsController c;

  /// Pick provider + model for a role. Switching to a cloud provider asks first; then the model
  /// is tried on the job before it is used, and a failed check offers to pick another.
  Future<void> chooseModel(String role, String title) async {
    final now = c.role(role);
    String? pid = now['provider'] as String?, model = now['model'] as String?;
    while (true) {
      // Loops back to the picker when a failed check is answered with "Pick another"
      if (!context.mounted) return;
      final picked = await showDialog<(String, String)>(
        context: context,
        builder: (_) => ModelPicker(api: c.api, title: title, providers: c.providers, role: role, provider: pid, model: model),
      );
      if (picked == null) return;
      final (newPid, newModel) = picked;
      (pid, model) = (newPid, newModel);
      if (!await _confirmCloud(role, title, now, newPid)) return;
      if (!context.mounted) return;
      final choice = await showDialog<String>(
        context: context,
        barrierDismissible: false,
        builder: (_) => CheckDialog(api: c.api, role: role, title: title, provider: newPid, model: newModel, choosing: true,
            onResult: (r) => c.checks[role] = r),
      );
      if (choice == 'use') return _useModel(role, title, newPid, newModel);
      if (choice != 'another') return;
    }
  }

  /// Re-run the check on the model a job uses now.
  Future<void> checkCurrent(String role, String title) async {
    final now = c.role(role);
    await showDialog<String>(
      context: context,
      barrierDismissible: false,
      builder: (_) => CheckDialog(api: c.api, role: role, title: title, provider: '${now['provider']}', model: '${now['model']}',
          onResult: (r) => c.checks[role] = r),
    );
    c.changed();
  }

  Future<bool> _confirmCloud(String role, String title, Map<String, dynamic> now, String pid) async {
    final p = c.provider(pid);
    final wasCloud = c.provider(now['provider'])?['cloud'] == true;
    if (p?['cloud'] == true && !wasCloud && context.mounted) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
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
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Keep it local')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Send to the cloud')),
          ],
        ),
      );
      return ok == true;
    }
    return true;
  }

  Future<void> _useModel(String role, String title, String pid, String model) async {
    if (!context.mounted) return;
    await runGuarded(
      context,
      () => c.useModel(role, pid, model),
      failure: 'Could not switch $title',
      success: (_) => '$title now uses $model${role == 'vision' ? '. It applies from the next indexing run.' : ''}',
    );
  }

  Future<void> setSpeech(String model) => runGuarded(
        context,
        () => c.setSpeech(model),
        failure: 'Could not switch the speech model',
        success: (_) => 'Speech uses whisper-$model from the next indexing run.',
      );

  Future<void> editProvider([Map<String, dynamic>? p]) async {
    final saved = await showDialog<Map<String, dynamic>>(context: context, builder: (_) => ProviderDialog(api: c.api, provider: p));
    if (saved == null) return;
    await c.load();
    await c.test(saved['id'] as String);
  }

  Future<void> removeProvider(Map<String, dynamic> p) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Remove ${p['name']}?'),
        content: const Text('Its address and API key are deleted from this laptop.', style: TextStyle(color: C.text3)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Remove')),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    await runGuarded(context, () => c.removeProvider(p['id'] as String), failure: 'Could not remove ${p['name']}');
  }

  Future<void> pull(String model) async {
    if (model.trim().isEmpty) return;
    await runGuarded(context, () => c.pull(model.trim()), failure: 'Could not download ${model.trim()}');
  }
}
