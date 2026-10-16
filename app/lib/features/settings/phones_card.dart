import 'package:flutter/material.dart';

import '../../core/errors/run_guarded.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/cards.dart';
import 'general_controller.dart';
import 'pair_dialog.dart';

/// Phones paired with this laptop, and pairing a new one.
class PhonesCard extends StatelessWidget {
  const PhonesCard({super.key, required this.c, required this.lan});
  final GeneralController c;
  final bool lan; // the server accepts phones (lumen serve --lan)

  Future<void> _pair(BuildContext context) async {
    final r = await runGuarded(context, c.api.pairStart, failure: 'Could not start pairing');
    if (r == null || !context.mounted) return;
    await showDialog<void>(
      context: context,
      builder: (_) => PairDialog(code: '${r['code']}', address: '${r['address']}', lan: r['lan'] == true),
    );
    if (context.mounted) await runGuarded(context, c.refreshDevices, failure: 'Could not list the phones');
  }

  @override
  Widget build(BuildContext context) => SectionCard(
        title: 'Paired phones',
        trailing: OutlinedButton(
          onPressed: () => _pair(context),
          style: OutlinedButton.styleFrom(minimumSize: const Size(0, 36)),
          child: const Text('Pair a phone'),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (!lan)
            const Padding(
              padding: EdgeInsets.only(bottom: 8),
              child: Text('Phones can only connect when the server runs with --lan.', style: TextStyle(fontSize: 13, color: C.accent)),
            ),
          if (c.devices.isEmpty) const Text('No phones paired.', style: TextStyle(fontSize: 13, color: C.muted)),
          for (final d in c.devices)
            Row(children: [
              const Icon(Icons.smartphone, size: 18, color: C.text3),
              const SizedBox(width: 10),
              Expanded(child: Text('${d['name']}')),
              TextButton(
                onPressed: () => runGuarded(context, () => c.unpair('${d['id']}'), failure: 'Could not remove ${d['name']}'),
                child: const Text('Remove'),
              ),
            ]),
        ]),
      );
}
