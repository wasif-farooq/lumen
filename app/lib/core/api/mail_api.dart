import '../models/json.dart';
import '../models/mail.dart';
import '../models/view.dart';
import 'api_client.dart';

/// Mailboxes (added and removed on the laptop only) and indexed mail.
mixin MailApi on ApiClient {
  Future<List<MailAccount>> mailAccounts() async =>
      [for (final a in listOf(await getJson('/api/mail/accounts'))) MailAccount.fromJson(a)];

  /// Server settings for an address (known providers), to fill in the form.
  Future<Map<String, dynamic>> mailGuess(String email) async => mapOf(await getJson('/api/mail/guess', {'email': email}));

  /// Signs in first, so a wrong password is said now; that can take a while on a slow server.
  Future<MailAccount> addMailAccount(Map<String, Object> body) async =>
      MailAccount.fromJson(mapOf(await sendJson('POST', '/api/mail/accounts', body, const Duration(seconds: 75))));

  Future<void> removeMailAccount(String id) => sendJson('DELETE', '/api/mail/accounts/$id');

  Future<void> syncMail() => sendJson('POST', '/api/mail/sync');

  Future<MailMessage> mail(int id) async => MailMessage.fromJson(mapOf(await getJson('/api/mail/messages/$id')));

  /// Fetched from the mail server, then shown like a file.
  Future<ViewInfo> mailAttachment(int id, int idx) async =>
      ViewInfo.fromJson(mapOf(await sendJson('POST', '/api/mail/messages/$id/attachments/$idx', null, const Duration(seconds: 75))));
}
