/// Reading the server's JSON safely: a nested object or list, or an empty one when it is
/// missing or of another type.
library;

Map<String, dynamic> mapOf(Object? value) => value is Map ? Map<String, dynamic>.from(value) : const {};

List<Map<String, dynamic>> listOf(Object? value) =>
    [for (final v in value is List ? value : const []) if (v is Map) Map<String, dynamic>.from(v)];

num numOf(Object? value) => value is num ? value : 0;
