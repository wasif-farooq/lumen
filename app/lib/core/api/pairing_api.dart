import 'api_client.dart';

/// Pairing phones with the laptop.
mixin PairingApi on ApiClient {
  Future<Map<String, dynamic>> pairStart() async => Map<String, dynamic>.from(await sendJson('POST', '/api/pair/start') as Map);
  Future<Map<String, dynamic>> pair(String code, String name) async =>
      Map<String, dynamic>.from(await sendJson('POST', '/api/pair', {'code': code, 'name': name}) as Map);
  Future<List<Map<String, dynamic>>> devices() async =>
      [for (final d in await getJson('/api/devices') as List) Map<String, dynamic>.from(d as Map)];
  Future<void> unpair(String id) => sendJson('DELETE', '/api/devices/$id');
}
