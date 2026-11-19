import 'dart:async';
import 'dart:convert';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tokenlogue_dart/data/vault.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Map<String, dynamic> record;
  late Completer<bool> decision;
  late Completer<void> promptOpen;
  late ProfileVault vault;
  late String binding;
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  setUp(() {
    record = {
      'version': 1,
      'id': 'unit-profile',
      'dek': base64Encode(List.filled(32, 7)),
      'salt': base64Encode(List.filled(16, 8)),
      'verifier': 'unit-old-verifier',
      'attempts': 0,
      'credentials': {
        'vsegpt': {'key': 'sk-or-visLOCAL_TEST'},
      },
    };
    decision = Completer<bool>();
    promptOpen = Completer<void>();
    binding = 'unit-profile';
    vault = ProfileVault(readBinding: () async => binding);
    messenger.setMockMethodCallHandler(ProfileVault.channel, (call) async {
      switch (call.method) {
        case 'read':
          return Uint8List.fromList(utf8.encode(jsonEncode(record)));
        case 'write':
          record =
              jsonDecode(utf8.decode(call.arguments as Uint8List))
                  as Map<String, dynamic>;
          return null;
        case 'recoveryAvailable':
          return true;
        case 'cancelDevice':
          return null;
        case 'authenticateDevice':
          promptOpen.complete();
          return decision.future;
        default:
          throw MissingPluginException();
      }
    });
  });
  tearDown(
    () => messenger.setMockMethodCallHandler(ProfileVault.channel, null),
  );
  test(
    'a late positive callback after background revocation cannot change the PIN or access bindings',
    () async {
      final original = jsonEncode(record);
      final pending = vault.requestRecovery('synthetic local challenge');
      await promptOpen.future;
      vault.revokeRecovery();
      decision.complete(true);
      expect(await pending, isFalse);
      expect(await vault.replacePin('0064'), isFalse);
      expect(jsonEncode(record), original);
    },
  );
  test(
    'database replacement during device authentication discards the result',
    () async {
      final pending = vault.requestRecovery('unit');
      await promptOpen.future;
      binding = 'replacement-db';
      decision.complete(true);
      expect(await pending, isFalse);
      binding = 'unit-profile';
      expect(await vault.replacePin('0041'), isFalse);
      expect(record['verifier'], 'unit-old-verifier');
    },
  );
  test(
    'recovery grant is one-use and tied to the same protected profile',
    () async {
      final pending = vault.requestRecovery('unit');
      await promptOpen.future;
      decision.complete(true);
      expect(await pending, isTrue);
      final slots = jsonEncode(record['credentials']), dek = record['dek'];
      record['id'] = 'different';
      expect(await vault.replacePin('0012'), isFalse);
      record['id'] = 'unit-profile';
      expect(
        await vault.replacePin('0012'),
        isFalse,
        reason: 'a rejected binding consumes the grant',
      );
      vault.revokeRecovery();
      record['id'] = 'unit-profile';
      decision = Completer<bool>();
      promptOpen = Completer<void>();
      final fresh = vault.requestRecovery('unit');
      await promptOpen.future;
      decision.complete(true);
      expect(await fresh, isTrue);
      expect(await vault.replacePin('0012'), isTrue);
      expect(record['verifier'], isNot('unit-old-verifier'));
      expect(record['dek'], dek);
      expect(jsonEncode(record['credentials']), slots);
      expect(await vault.replacePin('0099'), isFalse);
    },
  );
}
