import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../core/errors/run_guarded.dart';
import '../../core/format.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/cards.dart';
import '../../shared/widgets/common.dart';
import '../../shared/widgets/error_views.dart';
import 'add_mailbox_dialog.dart';
import 'mail_controller.dart';

/// Settings → Mail: connected mailboxes, how their reading is going, adding and removing them.
class MailSettings extends StatefulWidget {
  const MailSettings({super.key, required this.state});
  final AppState state;

  @override
  State<MailSettings> createState() => _MailSettingsState();
}

class _MailSettingsState extends State<MailSettings> {
  late final c = MailController(widget.state.api)..load();

  @override
  void dispose() {
    c.dispose();
    super.dispose();
  }

  Future<void> _add() async {
    final added = await showDialog<bool>(context: context, builder: (_) => AddMailboxDialog(c: c));
    if (added == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Mailbox connected. Reading its mail now…')));
    }
  }

  Future<void> _remove(MailAccount a) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('Remove ${a.email}?'),
        content: const Text(
          'Lumen forgets this mailbox: its password, its indexed mail and any attachments you opened. '
          'Nothing in the mailbox itself is touched.',
          style: TextStyle(color: C.text3),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Remove')),
        ],
      ),
    );
    if (ok == true && mounted) {
      await runGuarded(context, () => c.remove(a.id), failure: 'Could not remove ${a.email}', success: (_) => '${a.email} removed');
    }
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: c,
        builder: (context, _) => ListView(
          padding: const EdgeInsets.fromLTRB(32, 20, 32, 40),
          children: [
            const Text(
              'Mail from connected mailboxes is found next to your files, in search and in chat. '
              'Lumen only reads it: nothing in your mailboxes is changed. Trash, Spam and Drafts are left out.',
              style: TextStyle(color: C.text3),
            ),
            if (c.loadError != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: ErrorCard(error: c.loadError!, title: "Couldn't load the mailboxes", onRetry: c.load),
              ),
            const SizedBox(height: 24),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 760),
              child: SectionCard(
                title: 'Mailboxes',
                trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                  if (c.accounts.isNotEmpty)
                    TextButton.icon(
                      onPressed: () => runGuarded(context, c.syncNow, failure: 'Could not start reading mail'),
                      icon: const Icon(Icons.sync, size: 18),
                      label: const Text('Sync now'),
                    ),
                  const SizedBox(width: 6),
                  OutlinedButton(
                    onPressed: _add,
                    style: OutlinedButton.styleFrom(minimumSize: const Size(0, 36)),
                    child: const Text('Add a mailbox'),
                  ),
                ]),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  if (c.loaded && c.accounts.isEmpty && c.loadError == null)
                    const Text(
                      'No mailboxes yet. Gmail, Yahoo, iCloud and Fastmail need an app password; '
                      'any other mail server works with its IMAP settings.',
                      style: TextStyle(fontSize: 13, color: C.muted),
                    ),
                  for (final (i, a) in c.accounts.indexed) ...[
                    if (i > 0) const Divider(height: 24),
                    _AccountRow(account: a, onRemove: () => _remove(a)),
                  ],
                ]),
              ),
            ),
          ],
        ),
      );
}

class _AccountRow extends StatelessWidget {
  const _AccountRow({required this.account, required this.onRemove});
  final MailAccount account;
  final VoidCallback onRemove;

  String get _status {
    final a = account;
    final count = '${a.mails} ${a.mails == 1 ? 'mail' : 'mails'} indexed';
    return switch (a.state) {
      'syncing' => 'Reading${a.folder != null ? ' ${a.folder}' : ''}… $count',
      'error' => a.error ?? 'Could not read this mailbox.',
      'ok' => '$count · checked ${humanDate(a.last ?? 0)}',
      _ => '$count · waiting to be read',
    };
  }

  @override
  Widget build(BuildContext context) {
    final a = account;
    final color = switch (a.state) { 'error' => C.red, 'ok' => C.green, _ => C.accent };
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Padding(padding: EdgeInsets.only(top: 2), child: Icon(Icons.mail_outline, size: 20, color: C.text3)),
      const SizedBox(width: 12),
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(a.email, style: const TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 2),
          Text('${a.host}:${a.port}', style: monoStyle(size: 12)),
          const SizedBox(height: 6),
          Row(children: [
            StatusDot(color: color),
            const SizedBox(width: 8),
            Expanded(child: Text(_status, style: TextStyle(fontSize: 13, color: a.state == 'error' ? C.red : C.text3))),
          ]),
        ]),
      ),
      TextButton(onPressed: onRemove, child: const Text('Remove')),
    ]);
  }
}
