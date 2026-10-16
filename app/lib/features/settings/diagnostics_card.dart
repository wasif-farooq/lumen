import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/errors/run_guarded.dart';
import '../../core/logging/log.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/cards.dart';
import 'general_controller.dart';

/// When something goes wrong: where the logs are, and a summary to paste into a bug report.
class DiagnosticsCard extends StatelessWidget {
  const DiagnosticsCard({super.key, required this.c});
  final GeneralController c;

  Future<void> _openLogs(BuildContext context) => runGuarded(
        context,
        () async {
          final folder = Log.folder!;
          await folder.create(recursive: true);
          final r = await Process.run(Platform.isMacOS ? 'open' : (Platform.isWindows ? 'explorer' : 'xdg-open'), [folder.path]);
          if (r.exitCode != 0 && !Platform.isWindows) throw ProcessException('xdg-open', [folder.path], '${r.stderr}', r.exitCode);
        },
        failure: 'Could not open the logs folder',
      );

  Future<void> _copy(BuildContext context) => runGuarded(
        context,
        () async => Clipboard.setData(ClipboardData(text: await c.diagnostics())),
        failure: 'Could not collect diagnostics',
        success: (_) => 'Diagnostics copied. Paste them into a bug report; they contain file names, no keys.',
      );

  @override
  Widget build(BuildContext context) {
    final folder = Log.folder;
    return SectionCard(
      title: 'Problems',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Lumen keeps logs of what the app and the server did. They help find out what went wrong.',
            style: TextStyle(fontSize: 13, color: C.muted)),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          if (folder != null)
            OutlinedButton.icon(
              onPressed: () => _openLogs(context),
              icon: const Icon(Icons.folder_open_outlined, size: 16),
              label: const Text('Open logs'),
            ),
          OutlinedButton.icon(
            onPressed: () => _copy(context),
            icon: const Icon(Icons.content_copy_outlined, size: 16),
            label: const Text('Copy diagnostics'),
          ),
        ]),
      ]),
    );
  }
}
