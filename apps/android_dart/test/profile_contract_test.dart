import 'dart:convert';
import 'dart:typed_data';
import 'package:cryptography/cryptography.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tokenlogue_dart/data/chat_store.dart';
import 'package:tokenlogue_dart/data/vault.dart';

void main() {
  test(
    'four ASCII digits and PBKDF2-HMAC-SHA256 compatibility with fixed salt',
    () async {
      expect(validPin('0042'), isTrue);
      expect(validPin('１２３４'), isFalse);
      expect(validPin('0042\n'), isFalse);
      expect(
        await pinDigest('0042', base64Encode(List.generate(16, (i) => i))),
        'mj8Uk1lF7SLS70PvzppZDceQEIBGQtufTiYwfc03sp4=',
      );
    },
  );
  test(
    'GCM authenticates the profile, record, role, revision and tag including empty and Unicode text',
    () async {
      final key = List.generate(32, (i) => i);
      final f = FieldCipher(UnlockedProfile('synthetic-A', SecretKey(key), {}));
      final other = FieldCipher(
        UnlockedProfile('synthetic-B', SecretKey(key), {}),
      );
      for (final text in ['', '  план\n🌲  ']) {
        final box = await f.seal(text, 'record', 'turn:user', 3);
        expect(await f.open(box, 'record', 'turn:user', 3), text);
        for (final wrong in [
          () => f.open(box, 'other', 'turn:user', 3),
          () => f.open(box, 'record', 'turn:assistant', 3),
          () => f.open(box, 'record', 'turn:user', 4),
          () => other.open(box, 'record', 'turn:user', 3),
        ]) {
          await expectLater(
            wrong(),
            throwsA(isA<SecretBoxAuthenticationError>()),
          );
        }
        final corrupt = Uint8List.fromList(box);
        corrupt.last ^= 1;
        await expectLater(
          f.open(corrupt, 'record', 'turn:user', 3),
          throwsA(isA<SecretBoxAuthenticationError>()),
        );
      }
    },
  );
}
