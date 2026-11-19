import 'dart:io';
import 'package:cryptography/cryptography.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:tokenlogue_dart/data/chat_store.dart';
import 'package:tokenlogue_dart/data/journal.dart';
import 'package:tokenlogue_dart/data/vault.dart';

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  test(
    'schema upgrade rolls back a partial DDL failure and resumes without losing a draft, message or reserved attempt',
    () async {
      final dir = await Directory.systemTemp.createTemp(
        'tokenlogue-dart-migration-',
      );
      try {
        await databaseFactory.setDatabasesPath(dir.path);
        final profile = UnlockedProfile(
              'unit-binding',
              SecretKey(List.filled(32, 9)),
              {},
            ),
            cipher = FieldCipher(profile);
        final path = await ChatStore.location(),
            ddl = (await File('test/fixtures/schema_v1.sql').readAsString())
                .split('\n')
                .where((s) => !s.startsWith('--'))
                .join('\n')
                .split(';');
        var db = await openDatabase(
          path,
          version: 1,
          onCreate: (tx, _) async {
            for (final sql in ddl.where((s) => s.trim().isNotEmpty)) {
              await tx.execute(sql);
            }
          },
        );
        await db.transaction((tx) async {
          await tx.insert('profile', {'id': profile.id});
          await tx.insert('chats', {
            'id': 'c',
            'title': await cipher.seal('Trip', 'c', 'title', 1),
            'title_rev': 1,
            'provider': 'openrouter',
            'model': 'openrouter/free',
            'free': 1,
            'created': 0,
            'token_limit': 8192,
          });
          await tx.insert('drafts', {
            'chat': 'c',
            'rev': 3,
            'body': await cipher.seal('  Notes 🌱\n', 'c', 'draft', 3),
          });
          await tx.insert('turns', {'id': 't', 'chat': 'c', 'created': 0});
          await tx.insert('messages', {
            'id': 'm',
            'turn_id': 't',
            'role': 'user',
            'body': await cipher.seal('unit', 'm', 't:user', 1),
            'ordinal': 0,
          });
          for (final id in ['a', 'conflict']) {
            await tx.insert('attempts', {
              'id': id,
              'turn_id': 't',
              'provider': 'openrouter',
              'currency': 'USD',
              'requested_model': 'openrouter/free',
              'state': 'pending',
              'reserved_tokens': 50,
              'reserved_cost': '0',
              'snapshot': await cipher.seal('[]', id, 'dispatch', 1),
            });
          }
        });
        await db.close();
        await expectLater(
          ChatStore.open(profile),
          throwsA(isA<DatabaseException>()),
        );
        db = await openDatabase(path);
        expect(await db.getVersion(), 1);
        expect(
          (await db.rawQuery(
            'PRAGMA table_info(chats)',
          )).any((r) => r['name'] == 'response_limit'),
          isFalse,
        );
        await db.delete('attempts', where: 'id=?', whereArgs: ['conflict']);
        await db.close();
        for (var cycle = 0; cycle < 2; cycle++) {
          final store = await ChatStore.open(profile);
          expect((await store.chats()).single.draft, '  Notes 🌱\n');
          expect((await store.chats()).single.revision, 3);
          expect((await store.history('c')).single.body, 'unit');
          final attempt = (await store.journal()).single;
          expect(attempt['reserved_tokens'], 50);
          expect(attempt['state'], 'unknown');
          expect(
            (await store.db.rawQuery(
              'PRAGMA integrity_check',
            )).single.values.single,
            'ok',
          );
          expect(await store.db.rawQuery('PRAGMA foreign_key_check'), isEmpty);
          await store.db.close();
        }
      } finally {
        await dir.delete(recursive: true);
      }
    },
  );
}
