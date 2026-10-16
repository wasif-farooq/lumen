import 'api_client.dart';
import 'chats_api.dart';
import 'files_api.dart';
import 'index_api.dart';
import 'pairing_api.dart';
import 'providers_api.dart';
import 'system_api.dart';

export 'api_error.dart';

/// Everything the app asks `lumen serve`, one area per mixin. On the laptop: no token.
/// Phones: a paired token.
class Api extends ApiClient with SystemApi, ChatsApi, FilesApi, IndexApi, ProvidersApi, PairingApi {
  Api(super.base, {super.token, super.client});
}
