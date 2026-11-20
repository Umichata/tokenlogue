import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tokenlogue_dart/data/vault.dart';
import 'package:tokenlogue_dart/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  Uint8List? stored;
  var elapsed = 10000;
  setUp(() {
    stored = null;
    elapsed = 10000;
    messenger.setMockMethodCallHandler(ProfileVault.channel, (call) async {
      switch (call.method) {
        case 'language':
          return 'en';
        case 'deleting':
        case 'recoveryAvailable':
          return false;
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
  });
  tearDown(
    () => messenger.setMockMethodCallHandler(ProfileVault.channel, null),
  );

  test(
    'a one-digit difference is rejected and the third attempt persists a five-minute pause',
    () async {
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
  testWidgets(
    'ordinary sign-in with a different last digit leaves the workspace locked',
    (tester) async {
      final data = {
        'version': 1,
        'id': 'pin-widget-fixture',
        'dek': base64Encode(List.filled(32, 7)),
        'salt': base64Encode(List.generate(16, (i) => i)),
        'verifier': 'mj8Uk1lF7SLS70PvzppZDceQEIBGQtufTiYwfc03sp4=',
        'attempts': 0,
        'credentials': <String, Object?>{},
      };
      stored = Uint8List.fromList(utf8.encode(jsonEncode(data)));
      await tester.pumpWidget(const Tokenlogue());
      final field = find.byWidgetPredicate(
        (w) => w is TextField && w.obscureText,
      );
      for (var i = 0; i < 100 && field.evaluate().isEmpty; i++) {
        await tester.pump(const Duration(milliseconds: 30));
        await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 15)),
        );
      }
      expect(field, findsOneWidget);
      // The independent reference verifier above was produced for the fixture 0042.
      await tester.enterText(field, '0043');
      await tester.pump();
      final submit = find.widgetWithText(FilledButton, 'Sign in');
      await tester.ensureVisible(submit);
      await tester.pumpAndSettle();
      await tester.tap(submit);
      final notice = find.text('Incorrect PIN. Attempts remaining 2.');
      for (var i = 0; i < 250 && notice.evaluate().isEmpty; i++) {
        await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 40)),
        );
        await tester.pump(const Duration(milliseconds: 20));
      }
      expect(notice, findsOneWidget);
      expect(find.byType(NavigationBar), findsNothing);
      expect(jsonDecode(utf8.decode(stored!))['attempts'], 1);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
