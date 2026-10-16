import 'package:flutter/material.dart';

import '../../core/models/json.dart';
import '../../shared/theme.dart';
import 'provider_badge.dart';

/// One job (chat, images & video, speech): the model it uses, where, and its last check.
class RoleRow extends StatelessWidget {
  const RoleRow({super.key, required this.icon, required this.title, required this.desc, required this.model, this.provider, this.local = false, this.onChange, this.onCheck, this.check, this.trailing});
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
                          : 'Check failed: ${listOf(check!['checks']).lastWhere((c) => c['ok'] != true, orElse: () => const {'detail': ''})['detail']}',
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
            ProviderBadge(cloud: !local && cloud),
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
