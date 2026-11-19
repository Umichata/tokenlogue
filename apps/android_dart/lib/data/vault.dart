import 'dart:convert';
import 'dart:isolate';
import 'dart:math';

import 'package:cryptography/cryptography.dart';
import 'package:cryptography/helpers.dart';
import 'package:flutter/services.dart';
import 'package:synchronized/synchronized.dart';

import '../domain/provider.dart';

Uint8List randomBytes(int length) {
  final random = Random.secure();
  return Uint8List.fromList(List.generate(length, (_) => random.nextInt(256)));
}

bool validPin(String pin) =>
    pin.length == 4 && pin.codeUnits.every((n) => n >= 48 && n <= 57);

Future<String> pinDigest(String pin, String salt) async {
  if (!validPin(pin)) throw const FormatException('pin');
  return Isolate.run(() async {
    final algorithm = Pbkdf2(
      macAlgorithm: Hmac.sha256(),
      iterations: 600000,
      bits: 256,
    );
    final result = await algorithm.deriveKey(
      secretKey: SecretKey(ascii.encode(pin)),
      nonce: base64Decode(salt),
    );
    return base64Encode(await result.extractBytes());
  });
}

class ProfileVault {
  static const channel = MethodChannel(
    'io.github.umichata.tokenlogue.dart.vault.v1/platform',
  );
  final _writes = Lock();

  Future<Map<String, dynamic>?> _read() async {
    final bytes = await channel.invokeMethod<Uint8List>('read');
    if (bytes == null) return null;
    final record = jsonDecode(utf8.decode(bytes)) as Map<String, dynamic>;
    if (record['version'] != 1 ||
        record['id'] is! String ||
        base64Decode(record['dek'] as String).length != 32) {
      throw const FormatException('profile');
    }
    return record;
  }

  Future<void> _write(Map<String, dynamic> record) =>
      channel.invokeMethod<void>(
        'write',
        Uint8List.fromList(utf8.encode(jsonEncode(record))),
      );

  Future<bool> exists() async => await _read() != null;

  Future<void> register(String pin, String credential, bool verified) =>
      _writes.synchronized(() async {
        final service = Service.detect(credential);
        if (service == null || !validPin(pin) || await _read() != null) {
          throw StateError('registration');
        }
        final salt = base64Encode(randomBytes(16));
        await _write({
          'version': 1,
          'id': base64UrlEncode(randomBytes(18)),
          'dek': base64Encode(randomBytes(32)),
          'salt': salt,
          'verifier': await pinDigest(pin, salt),
          'attempts': 0,
          'credentials': {
            service.name: {'key': credential.trim(), 'verified': verified},
          },
        });
      });

  /// Returns the profile only after a successful PIN check and durable counter update.
  Future<UnlockedProfile?> unlock(String pin) => _writes.synchronized(() async {
    final record = await _read();
    if (record == null) throw StateError('missing_profile');
    final clock = await channel.invokeListMethod<int>('clock');
    if (clock == null || clock.length != 2) throw StateError('clock');
    final elapsed = clock[0], boot = clock[1];
    if (record['attempts'] == 3) {
      final deadline = record['deadline'] as int;
      final remaining = record['boot'] == boot
          ? deadline - elapsed
          : 300000 - elapsed;
      if (remaining > 0) throw PinLocked(remaining);
      record['attempts'] = 0;
    }
    final digest = validPin(pin)
        ? await pinDigest(pin, record['salt'] as String)
        : '';
    if (!constantTimeBytesEquality.equals(
      ascii.encode(digest),
      ascii.encode(record['verifier'] as String),
    )) {
      record['attempts'] = (record['attempts'] as int) + 1;
      if (record['attempts'] == 3) {
        record['boot'] = boot;
        record['deadline'] = elapsed + 300000;
      }
      await _write(record);
      if (record['attempts'] == 3) throw const PinLocked(300000);
      return null;
    }
    record['attempts'] = 0;
    record.remove('boot');
    record.remove('deadline');
    await _write(record);
    return UnlockedProfile(
      record['id'] as String,
      SecretKey(base64Decode(record['dek'] as String)),
      Map<String, dynamic>.from(record['credentials'] as Map),
    );
  });

  Future<void> saveKey(
    UnlockedProfile profile,
    Service service,
    String value,
    bool verified,
  ) => _writes.synchronized(() async {
    if (Service.detect(value) != service || profile.disposed) {
      throw StateError('credential');
    }
    final record = await _read();
    if (record == null || record['id'] != profile.id || profile.disposed) {
      throw StateError('session');
    }
    final slot = {'key': value.trim(), 'verified': verified};
    (record['credentials'] as Map)[service.name] = slot;
    await _write(record);
    if (!profile.disposed) profile.credentials[service.name] = slot;
  });
}

class PinLocked implements Exception {
  const PinLocked(this.milliseconds);
  final int milliseconds;
}

class UnlockedProfile {
  UnlockedProfile(this.id, this.dek, this.credentials);
  final String id;
  final SecretKey dek;
  final Map<String, dynamic> credentials;
  bool disposed = false;
  String? keyFor(Service s) =>
      disposed ? null : credentials[s.name]?['key'] as String?;
  void dispose() {
    disposed = true;
    credentials.clear();
    dek.destroy();
  }
}
