import 'package:flutter/material.dart';

import '../../core/app_state.dart';
import '../../core/errors/errors.dart';
import '../../core/format.dart';
import '../../shared/theme.dart';
import '../../shared/widgets/marked_text.dart';
import 'finder.dart';

/// An indexed mail: who, when, its attachments (opened from the mail server) and its text, with
/// the search words and "Find" marked.
class MailView extends StatefulWidget {
  const MailView({super.key, required this.api, required this.info, required this.onAttachment, this.terms = const [], required this.finder});
  final Api api;
  final ViewInfo info; // path "mail:<id>"
  final void Function(MailMessage mail, MailAttachment a) onAttachment;
  final List<String> terms;
  final Finder finder;

  static int idOf(String path) => int.tryParse(path.replaceFirst('mail:', '')) ?? -1;

  @override
  State<MailView> createState() => _MailViewState();
}

class _MailViewState extends State<MailView> {
  late final Future<MailMessage> mail = widget.api.mail(MailView.idOf(widget.info.path));

  @override
  Widget build(BuildContext context) => FutureBuilder<MailMessage>(
        future: mail,
        builder: (context, snap) {
          if (snap.hasError) return Center(child: Text(userMessage(snap.error!), style: const TextStyle(color: C.text3)));
          if (!snap.hasData) return const Center(child: CircularProgressIndicator(color: C.accent));
          final m = snap.data!;
          return ListenableBuilder(
            listenable: widget.finder,
            builder: (context, _) => _mail(m, [...widget.terms, if (widget.finder.query.isNotEmpty) widget.finder.query]),
          );
        },
      );

  Widget _mail(MailMessage m, List<String> terms) => SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 40),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 760),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SelectableText(m.subject, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600)),
              const SizedBox(height: 12),
              _line('From', m.senderName == m.sender || m.senderName.isEmpty ? m.sender : '${m.senderName} <${m.sender}>'),
              if (m.recipients.isNotEmpty) _line('To', m.recipients),
              _line('Date', fullDate(m.date)),
              _line('Folder', m.folder),
              if (m.attachments.isNotEmpty) ...[
                const SizedBox(height: 12),
                Wrap(spacing: 8, runSpacing: 8, children: [
                  for (final a in m.attachments)
                    ActionChip(
                      avatar: const Icon(Icons.attach_file, size: 16, color: C.text3),
                      label: Text('${a.name} · ${humanSize(a.size)}'),
                      tooltip: 'Open the attachment',
                      onPressed: () => widget.onAttachment(m, a),
                    ),
                ]),
              ],
              const Divider(height: 32),
              MarkedText(m.text.isEmpty ? '(This mail has no text.)' : m.text, terms: terms,
                  style: const TextStyle(fontSize: 14.5, height: 1.6, color: C.text2)),
            ]),
          ),
        ),
      );

  Widget _line(String label, String value) => Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: 64, child: Text(label, style: const TextStyle(fontSize: 13, color: C.muted))),
          Expanded(child: SelectableText(value, style: const TextStyle(fontSize: 13, color: C.text2))),
        ]),
      );
}
