import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_error.dart';
import '../../core/errors/errors.dart';
import '../../shared/theme.dart';
import 'mail_controller.dart';

/// Connecting a mailbox: the address and an (app) password; the server is filled in for known
/// providers and can be changed under "Server settings".
class AddMailboxDialog extends StatefulWidget {
  const AddMailboxDialog({super.key, required this.c});
  final MailController c;

  @override
  State<AddMailboxDialog> createState() => _AddMailboxDialogState();
}

class _AddMailboxDialogState extends State<AddMailboxDialog> {
  final email = TextEditingController();
  final password = TextEditingController();
  final host = TextEditingController();
  final port = TextEditingController(text: '993');
  final user = TextEditingController();
  String security = 'ssl';
  int sinceDays = 365;
  String hint = '';
  bool advanced = false, busy = false;
  String? error;
  String _guessedFor = '';

  static const periods = {30: 'Last month', 365: 'Last year', 1095: 'Last 3 years', 3650: 'Last 10 years'};

  /// Fill in the server for the address (unless the user typed their own).
  Future<void> _guess() async {
    final e = email.text.trim();
    if (!e.contains('@') || e == _guessedFor) return;
    _guessedFor = e;
    try {
      final g = await widget.c.api.mailGuess(e);
      if (!mounted || email.text.trim() != e) return;
      setState(() {
        host.text = '${g['host'] ?? ''}';
        port.text = '${g['port'] ?? 993}';
        security = '${g['security'] ?? 'ssl'}';
        hint = '${g['hint'] ?? ''}';
      });
    } on ApiError catch (_) {
      // the form still works: the server guesses again when the account is added
    }
  }

  Future<void> _connect() async {
    if (email.text.trim().isEmpty || password.text.isEmpty) {
      setState(() => error = 'Enter the address and the password.');
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await widget.c.add({
        'email': email.text.trim(),
        'password': password.text,
        'host': host.text.trim(),
        'port': int.tryParse(port.text.trim()) ?? 0,
        'security': security,
        'user': user.text.trim(),
        'since_days': sinceDays,
      });
      if (mounted) Navigator.pop(context, true);
    } on Object catch (e) {
      if (mounted) {
        setState(() {
          busy = false;
          error = [userMessage(e), if (e is ApiError && e.hint.isNotEmpty) e.hint].join('\n');
        });
      }
    }
  }

  @override
  void dispose() {
    for (final c in [email, password, host, port, user]) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Add a mailbox'),
        content: SizedBox(
          width: 440,
          child: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const Text(
                'Lumen only reads your mail, to find it next to your files. Nothing in the mailbox is changed. '
                'The password stays on this laptop.',
                style: TextStyle(fontSize: 13, color: C.text3),
              ),
              const SizedBox(height: 16),
              Focus(
                onFocusChange: (has) => has ? null : unawaited(_guess()),
                child: TextField(
                  controller: email,
                  autofocus: true,
                  decoration: const InputDecoration(labelText: 'Email address'),
                  onSubmitted: (_) => unawaited(_guess()),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: password,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'Password or app password'),
                onSubmitted: (_) => busy ? null : unawaited(_connect()),
              ),
              if (hint.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(hint, style: const TextStyle(fontSize: 12.5, color: C.accent)),
              ],
              const SizedBox(height: 12),
              DropdownButtonFormField<int>(
                initialValue: sinceDays,
                decoration: const InputDecoration(labelText: 'Index mail from'),
                items: [for (final e in periods.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
                onChanged: (v) => setState(() => sinceDays = v ?? 365),
              ),
              const SizedBox(height: 4),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: () => setState(() => advanced = !advanced),
                  icon: Icon(advanced ? Icons.expand_less : Icons.expand_more, size: 18),
                  label: const Text('Server settings'),
                ),
              ),
              if (advanced) ...[
                Row(children: [
                  Expanded(flex: 3, child: TextField(controller: host, decoration: const InputDecoration(labelText: 'IMAP server'))),
                  const SizedBox(width: 10),
                  Expanded(child: TextField(controller: port, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Port'))),
                ]),
                const SizedBox(height: 12),
                Row(children: [
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      initialValue: security,
                      decoration: const InputDecoration(labelText: 'Security'),
                      items: const [
                        DropdownMenuItem(value: 'ssl', child: Text('SSL/TLS')),
                        DropdownMenuItem(value: 'starttls', child: Text('STARTTLS')),
                        DropdownMenuItem(value: 'none', child: Text('None')),
                      ],
                      onChanged: (v) => setState(() => security = v ?? 'ssl'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(child: TextField(controller: user, decoration: const InputDecoration(labelText: 'User name (if not the address)'))),
                ]),
              ],
              if (error != null) ...[
                const SizedBox(height: 12),
                Text(error!, style: const TextStyle(color: C.red, fontSize: 13)),
              ],
            ]),
          ),
        ),
        actions: [
          TextButton(onPressed: busy ? null : () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(
            onPressed: busy ? null : _connect,
            child: busy
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: C.onAccent))
                : const Text('Connect'),
          ),
        ],
      );
}
