import 'api_client.dart';

/// The laptop's status, settings and diagnostics.
mixin SystemApi on ApiClient {
  Future<Map<String, dynamic>> hello() async => Map<String, dynamic>.from(await getJson('/api/hello') as Map);
  Future<Map<String, dynamic>> status() async => Map<String, dynamic>.from(await getJson('/api/status') as Map);
  Future<Map<String, dynamic>> settings() async => Map<String, dynamic>.from(await getJson('/api/settings') as Map);
  Future<Map<String, dynamic>> saveSettings(Map<String, dynamic> s) async =>
      Map<String, dynamic>.from(await sendJson('PUT', '/api/settings', s) as Map);
  Future<Map<String, dynamic>> diagnostics() async => Map<String, dynamic>.from(await getJson('/api/diagnostics') as Map);
}
