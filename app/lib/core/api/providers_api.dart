import 'api_client.dart';

/// Model providers, which model does each job, model checks and Ollama downloads.
mixin ProvidersApi on ApiClient {
  Future<Map<String, dynamic>> providers() async => Map<String, dynamic>.from(await getJson('/api/providers') as Map);
  Future<Map<String, dynamic>> saveProvider(Map<String, dynamic> p) async =>
      Map<String, dynamic>.from(await sendJson('POST', '/api/providers', p) as Map);
  Future<void> deleteProvider(String id) => sendJson('DELETE', '/api/providers/$id');
  Future<List<Map<String, dynamic>>> providerModels(String id) async =>
      [for (final m in await getJson('/api/providers/$id/models') as List) Map<String, dynamic>.from(m as Map)];
  Future<Map<String, dynamic>> testProvider(String id) async =>
      Map<String, dynamic>.from(await sendJson('POST', '/api/providers/$id/test') as Map);
  Future<Map<String, dynamic>> pullModel(String model) async =>
      Map<String, dynamic>.from(await sendJson('POST', '/api/providers/ollama/pull', {'model': model}) as Map);

  /// Try a model on a job before using it; a local model may need a minute to load.
  Future<Map<String, dynamic>> checkModel(String role, String provider, String model) async => Map<String, dynamic>.from(
      await sendJson('POST', '/api/models/check', {'role': role, 'provider': provider, 'model': model}, const Duration(minutes: 3))
          as Map);
  Future<Map<String, dynamic>> setRole(String role, String provider, String model) async =>
      Map<String, dynamic>.from(await sendJson('PUT', '/api/roles', {'role': role, 'provider': provider, 'model': model}) as Map);
}
