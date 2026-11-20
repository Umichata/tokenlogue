import 'dart:io';

import 'package:cryptography/cryptography.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite/sqflite.dart';
import 'package:tokenlogue_dart/data/chat_store.dart';
import 'package:tokenlogue_dart/data/journal.dart';
import 'package:tokenlogue_dart/data/providers.dart';
import 'package:tokenlogue_dart/data/session.dart';
import 'package:tokenlogue_dart/data/vault.dart';
import 'package:tokenlogue_dart/domain/catalogue.dart';
import 'package:tokenlogue_dart/presentation/theme.dart';
import 'package:tokenlogue_dart/presentation/workspace.dart';

void registerHistoryScenario() {
  testWidgets(
    'scroll a long encrypted chat and keep editing the same draft on Android',
    (tester) async {
      final original = await getDatabasesPath();
      final directory = await Directory.systemTemp.createTemp(
        'tokenlogue-history-',
      );
      await databaseFactory.setDatabasesPath(directory.path);
      final profile = UnlockedProfile(
        'history-qa',
        SecretKey(List.filled(32, 7)),
        {},
      );
      final store = await ChatStore.open(profile);
      final api = ProviderApi();
      // The fixture has no provider keys. Loading this workspace cannot refresh any account.
      final session = Session(profile, store, api);
      addTearDown(() async {
        await session.close();
        await databaseFactory.setDatabasesPath(original);
        await directory.delete(recursive: true);
      });
      await store.configure(
        id: 'trip',
        title: 'Journey',
        model: ModelChoice.router,
        tokens: 8192,
        output: 64,
        budget: null,
        skip: false,
        reconnect: false,
      );
      for (var i = 0; i < 48; i++) {
        final turn = 'turn-$i', id = 'message-$i';
        await store.db.insert('turns', {
          'id': turn,
          'chat': 'trip',
          'created': i,
        });
        await store.db.insert('messages', {
          'id': id,
          'turn_id': turn,
          'role': 'user',
          'ordinal': 0,
          'body': await store.crypto.seal(
            'Station $i',
            id,
            messageField('trip', turn, 'user'),
            2,
          ),
        });
      }
      await store.saveDraft('trip', 'Which station?', 0);
      await tester.pumpWidget(
        MaterialApp(
          theme: buildTheme(),
          home: Workspace(
            session: session,
            api: api,
            vault: ProfileVault(),
            t: (s) => s,
            onLock: () {},
            onDelete: () {},
            language: 'en',
            setLanguage: (_) {},
          ),
        ),
      );
      final editor = find.byWidgetPredicate(
        (w) => w is TextField && w.keyboardType == TextInputType.multiline,
      );
      final deadline = DateTime.now().add(const Duration(seconds: 25));
      while (editor.evaluate().isEmpty && DateTime.now().isBefore(deadline)) {
        await tester.pump(const Duration(milliseconds: 80));
      }
      expect(editor.hitTestable(), findsOneWidget);
      final history = find
          .descendant(
            of: find.byType(CustomScrollView).first,
            matching: find.byType(Scrollable),
          )
          .first;
      await tester.scrollUntilVisible(
        find.text('Station 47', findRichText: true),
        260,
        scrollable: history,
        maxScrolls: 160,
      );
      expect(editor.hitTestable(), findsOneWidget);
      expect(
        tester.widget<TextField>(editor).controller!.text,
        'Which station?',
      );
      await tester.enterText(editor, 'Station 47 is the last stop.');
      await session.flush();
      expect(
        (await store.chats()).single.draft,
        'Station 47 is the last stop.',
      );
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
