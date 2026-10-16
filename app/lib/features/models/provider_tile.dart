import 'package:flutter/material.dart';

import '../../shared/theme.dart';
import 'provider_badge.dart';

/// A provider: address, key, what uses it, and its connection test.
class ProviderTile extends StatelessWidget {
  const ProviderTile({super.key, required this.p, required this.test, required this.onTest, required this.onEdit, this.onRemove});
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
          ProviderBadge(cloud: p['cloud'] == true),
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
