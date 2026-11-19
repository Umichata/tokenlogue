import 'dart:convert';
import 'dart:isolate';
import 'dart:math';

import 'package:cryptography/cryptography.dart';
import 'package:cryptography/helpers.dart';
import 'package:flutter/services.dart';
import 'package:synchronized/synchronized.dart';

import '../domain/provider.dart';
import '../domain/pin_cooldown.dart';

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

  int _recoveryEpoch = 0;
  String? _grantedProfile;
  int? _expiresAt;
  final Stopwatch _timer = Stopwatch()..start();

  Future<bool> canRecover() async =>
      await channel.invokeMethod<bool>('recoveryAvailable') ?? false;

  void revokeRecovery() {
    _recoveryEpoch++;
    _grantedProfile = null;
    _expiresAt = null;
    channel.invokeMethod<void>('cancelDevice').catchError((Object _) {});
  }

  Future<bool> requestRecovery(String reason) async {
    revokeRecovery();
    final epoch = _recoveryEpoch;
    final initial = await _read();
    if (initial == null || epoch != _recoveryEpoch || !await canRecover()) {
      return false;
    }
    if (epoch != _recoveryEpoch) return false;
    final ok = await channel
        .invokeMethod<bool>('authenticateDevice', reason)
        .timeout(
          const Duration(seconds: 90),
          onTimeout: () {
            revokeRecovery();
            return false;
          },
        );
    if (ok != true || epoch != _recoveryEpoch) return false;
    _grantedProfile = initial['id'] as String;
    _expiresAt = _timer.elapsedMilliseconds + 120000;
    return true;
  }

  Future<bool> replacePin(String pin) => _writes.synchronized(() async {
    final epoch = _recoveryEpoch;
    final record = await _read();
    bool granted() =>
        record != null &&
        record['id'] == _grantedProfile &&
        epoch == _recoveryEpoch &&
        _expiresAt != null &&
        _timer.elapsedMilliseconds < _expiresAt!;
    if (!validPin(pin) || !granted()) return false;
    final salt = base64Encode(randomBytes(16));
    final verifier = await pinDigest(pin, salt);
    if (!granted()) return false;
    revokeRecovery();
    record!.addAll({'salt': salt, 'verifier': verifier, 'attempts': 0});
    record.remove('deadline');
    record.remove('boot');
    await _write(record);
    return true;
  });

  Future<void> register(String pin, String credential, bool verified) =>
      _writes.synchronized(() async {
        final service = Service.detect(credential);
        if (service == null || !validPin(pin) || await _read() != null) {
          throw StateError('registration');
        }
        final salt = base64Encode(randomBytes(16));
        await _write({
          'version': 1,
          'creating': true,
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
    final remaining = PinCooldown.normalize(record, elapsed, boot);
    if (remaining > 0) {
      await _write(record);
      throw PinLocked(remaining);
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
        PinCooldown.arm(record, elapsed, boot);
      }
      await _write(record);
      if (record['attempts'] == 3) throw const PinLocked(300000);
      return null;
    }
    PinCooldown.clear(record);
    await _write(record);
    return UnlockedProfile(
      record['id'] as String,
      SecretKey(base64Decode(record['dek'] as String)),
      Map<String, dynamic>.from(record['credentials'] as Map),
      creating: record['creating'] == true,
    );
  });

  Future<void> markReady(UnlockedProfile profile) =>
      _writes.synchronized(() async {
        final record = await _read();
        if (record == null || record['id'] != profile.id) {
          throw StateError('binding');
        }
        record.remove('creating');
        await _write(record);
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
  UnlockedProfile(this.id, this.dek, this.credentials, {this.creating = false});
  final bool creating;
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
