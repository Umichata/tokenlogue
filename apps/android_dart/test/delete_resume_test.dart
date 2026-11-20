import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:tokenlogue_dart/data/chat_store.dart';
import 'package:tokenlogue_dart/data/vault.dart';
import 'package:tokenlogue_dart/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  testWidgets(
    'pending deletion retries after restart or from the unfinished deletion screen',
    (tester) async {
      sqfliteFfiInit();
      databaseFactory = databaseFactoryFfi;
      late Directory directory;
      late String path;
      await tester.runAsync(() async {
        directory = await Directory.systemTemp.createTemp(
          'dart-delete-contract-',
        );
        await databaseFactory.setDatabasesPath(directory.path);
        path = await ChatStore.location();
        final db = await openDatabase(path);
        await db.execute(
          'CREATE TABLE disposable_fixture(id INTEGER PRIMARY KEY)',
        );
        await db.insert('disposable_fixture', {'id': 1});
        await db.close();
      });
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      var pending = true, finishes = 0, readsWhilePending = 0;
      messenger.setMockMethodCallHandler(ProfileVault.channel, (call) async {
        switch (call.method) {
          case 'language':
            return 'en';
          case 'recoveryAvailable':
            return false;
          case 'deleting':
            return pending;
          case 'finishDelete':
            finishes++;
            if (finishes < 3) throw PlatformException(code: 'interrupted');
            pending = false;
            return null;
          case 'read':
            if (pending) readsWhilePending++;
            return null;
          default:
            return null;
        }
      });
      addTearDown(() async {
        messenger.setMockMethodCallHandler(ProfileVault.channel, null);
        await directory.delete(recursive: true);
      });
      Future<void> waitUntil(bool Function() predicate) async {
        for (var i = 0; i < 100 && !predicate(); i++) {
          await tester.pump(const Duration(milliseconds: 20));
          await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 10)),
          );
        }
        expect(predicate(), isTrue);
      }

      await tester.pumpWidget(const Tokenlogue());
      await waitUntil(() => finishes == 1);
      expect(pending, isTrue);
      expect(find.byType(NavigationBar), findsNothing);
      expect(find.text('Check key'), findsNothing);
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpWidget(const Tokenlogue());
      await waitUntil(() => find.text('Finish deletion').evaluate().isNotEmpty);
      expect(finishes, 2);
      expect(find.text('Forgot PIN?'), findsNothing);
      await tester.dragUntilVisible(
        find.text('Finish deletion').hitTestable(),
        find.byType(ListView),
        const Offset(0, -160),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Finish deletion'));
      await waitUntil(() => find.text('Check key').evaluate().isNotEmpty);
      expect(finishes, 3);
      expect(readsWhilePending, 0);
      expect(pending, isFalse);
      await tester.runAsync(() async {
        expect(await databaseExists(path), isFalse);
      });
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
