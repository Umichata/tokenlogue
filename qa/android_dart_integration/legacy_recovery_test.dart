import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:tokenlogue_dart/data/chat_store.dart';
import 'package:tokenlogue_dart/data/vault.dart';
import 'package:tokenlogue_dart/main.dart' as app;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets(
    'Android 7 through 10 keeps PIN sign-in and explains unavailable system recovery',
    (tester) async {
      final sdk = await Process.run('/system/bin/getprop', [
        'ro.build.version.sdk',
      ]);
      final level = int.parse(sdk.stdout.toString().trim());
      expect(level, inInclusiveRange(24, 29));
      final vault = ProfileVault();
      expect(await vault.canRecover(), isFalse);
      // Only the isolated QA package gets this disposable, locally generated registration.
      // No secret is entered through the UI or copied from either release application.
      expect(await vault.exists(), isFalse);
      final testPin = Random.secure().nextInt(10000).toString().padLeft(4, '0');
      await vault.register(
        testPin,
        'sk-or-vis-local-fixture',
        false,
        canCommit: () => true,
      );
      final profile = (await vault.unlock(testPin))!;
      final store = await ChatStore.open(profile);
      await vault.markReady(profile);
      await store.db.close();
      profile.dispose();
      await ProfileVault.channel.invokeMethod<void>('setLanguage', 'en');
      app.main();
      final login = find.text('Sign in');
      final deadline = DateTime.now().add(const Duration(seconds: 30));
      while (login.evaluate().isEmpty && DateTime.now().isBefore(deadline)) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(login, findsWidgets);
      final words =
          jsonDecode(await rootBundle.loadString('assets/locales/en.json'))
              as Map<String, dynamic>;
      expect(
        find.text(words['recovery.unavailable'] as String),
        findsOneWidget,
      );
      await tester.ensureVisible(find.text('Forgot PIN?'));
      await tester.tap(find.text('Forgot PIN?'));
      await tester.pumpAndSettle();
      final button = find.widgetWithText(FilledButton, 'Confirm on device');
      expect(tester.widget<FilledButton>(button).onPressed, isNull);
    },
  );
}
