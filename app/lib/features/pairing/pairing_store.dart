import 'package:shared_preferences/shared_preferences.dart';

/// The laptop this phone is paired with: address, token and name, kept on the phone.
class Pairing {
  static Future<(String, String, String)?> load() async {
    final p = await SharedPreferences.getInstance();
    final base = p.getString('base'), token = p.getString('token');
    if (base == null || token == null) return null;
    return (base, token, p.getString('host') ?? 'laptop');
  }

  static Future<void> save(String base, String token, String host) async {
    final p = await SharedPreferences.getInstance();
    await p.setString('base', base);
    await p.setString('token', token);
    await p.setString('host', host);
  }

  static Future<void> clear() async {
    final p = await SharedPreferences.getInstance();
    await p.remove('token');
  }
}
