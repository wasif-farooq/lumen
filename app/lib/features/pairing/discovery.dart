import 'package:multicast_dns/multicast_dns.dart';

import '../../core/logging/log.dart';

const _log = Log('pairing');

/// A laptop found on this Wi-Fi.
class Found {
  final String name, address;
  Found(this.name, this.address);
}

/// Finds laptops running `lumen serve --lan` on this Wi-Fi (mDNS).
Future<List<Found>> discover({Duration timeout = const Duration(seconds: 4)}) async {
  final client = MDnsClient();
  final found = <String, Found>{};
  try {
    await client.start();
    await for (final ptr in client.lookup<PtrResourceRecord>(ResourceRecordQuery.serverPointer('_lumen._tcp.local')).timeout(timeout, onTimeout: (s) => s.close())) {
      await for (final srv in client.lookup<SrvResourceRecord>(ResourceRecordQuery.service(ptr.domainName)).timeout(const Duration(seconds: 2), onTimeout: (s) => s.close())) {
        await for (final ip in client.lookup<IPAddressResourceRecord>(ResourceRecordQuery.addressIPv4(srv.target)).timeout(const Duration(seconds: 2), onTimeout: (s) => s.close())) {
          final name = ptr.domainName.split('.').first;
          found[name] = Found(name, '${ip.address.address}:${srv.port}');
        }
      }
    }
  } on Object catch (e) {
    // Discovery is best effort; the user can type the address.
    _log.info('discovery stopped: $e');
  } finally {
    client.stop();
  }
  return found.values.toList();
}
