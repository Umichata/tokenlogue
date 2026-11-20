import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tokenlogue_dart/data/vault.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'a one-digit difference is rejected and the third attempt persists a five-minute pause',
    () async {
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      Uint8List? stored;
      var elapsed = 10000;
      messenger.setMockMethodCallHandler(ProfileVault.channel, (call) async {
        switch (call.method) {
          case 'read':
            return stored;
          case 'write':
            stored = Uint8List.fromList(call.arguments as Uint8List);
            return null;
          case 'clock':
            return [elapsed, 1];
          default:
            throw MissingPluginException();
        }
      });
      addTearDown(
        () => messenger.setMockMethodCallHandler(ProfileVault.channel, null),
      );

      final vault = ProfileVault();
      const registered = '0042', other = '0043';
      await vault.register(
        registered,
        'sk-or-vis-contract-fixture',
        false,
        canCommit: () => true,
      );
      for (final remaining in [2, 1]) {
        await expectLater(
          vault.unlock(other),
          throwsA(
            isA<PinRejected>().having(
              (e) => e.remaining,
              'remaining attempts',
              remaining,
            ),
          ),
        );
      }
      await expectLater(
        vault.unlock(other),
        throwsA(
          isA<PinLocked>().having(
            (e) => e.milliseconds,
            'initial duration',
            300000,
          ),
        ),
      );
      final reopened = ProfileVault();
      elapsed += 299999;
      await expectLater(
        reopened.unlock(registered),
        throwsA(
          isA<PinLocked>().having((e) => e.milliseconds, 'last millisecond', 1),
        ),
      );
      elapsed++;
      final unlocked = await reopened.unlock(registered);
      expect(unlocked, isNotNull);
      unlocked!.dispose();
      await expectLater(
        reopened.unlock(other),
        throwsA(
          isA<PinRejected>().having(
            (e) => e.remaining,
            'counter after successful login',
            2,
          ),
        ),
      );
    },
  );
}
