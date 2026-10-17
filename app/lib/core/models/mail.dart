import 'json.dart';

/// A connected mailbox and how its reading is going (never its password).
class MailAccount {
  final String id, email, host, security, user, state; // state: waiting | syncing | ok | error
  final int port, sinceDays, mails;
  final double? last; // last finished sync (seconds since 1970)
  final String? error, folder; // folder: being read now

  MailAccount.fromJson(Map<String, dynamic> j)
      : id = j['id'] as String? ?? '',
        email = j['email'] as String? ?? '',
        host = j['host'] as String? ?? '',
        security = j['security'] as String? ?? 'ssl',
        user = j['user'] as String? ?? '',
        state = j['state'] as String? ?? 'waiting',
        port = numOf(j['port']).toInt(),
        sinceDays = numOf(j['since_days']).toInt(),
        mails = numOf(j['mails']).toInt(),
        last = (j['last'] as num?)?.toDouble(),
        error = j['error'] as String?,
        folder = j['folder'] as String?;

  bool get syncing => state == 'syncing' || state == 'waiting';
}

class MailAttachment {
  final int idx, size;
  final String name, type;

  MailAttachment.fromJson(Map<String, dynamic> j)
      : idx = numOf(j['idx']).toInt(),
        size = numOf(j['size']).toInt(),
        name = j['name'] as String? ?? '',
        type = j['type'] as String? ?? '';
}

/// An indexed mail, as the viewer shows it.
class MailMessage {
  final int id;
  final String folder, sender, senderName, recipients, subject, text;
  final double date;
  final List<MailAttachment> attachments;

  MailMessage.fromJson(Map<String, dynamic> j)
      : id = numOf(j['id']).toInt(),
        folder = j['folder'] as String? ?? '',
        sender = j['sender'] as String? ?? '',
        senderName = j['sender_name'] as String? ?? '',
        recipients = j['recipients'] as String? ?? '',
        subject = j['subject'] as String? ?? '',
        text = j['text'] as String? ?? '',
        date = numOf(j['date']).toDouble(),
        attachments = [for (final a in listOf(j['attachments'])) MailAttachment.fromJson(a)];
}
