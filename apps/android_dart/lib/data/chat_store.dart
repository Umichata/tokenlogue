import 'dart:convert';
import 'dart:typed_data';
import 'package:cryptography/cryptography.dart';
import 'package:sqflite/sqflite.dart';
import '../domain/provider.dart';
import 'vault.dart';

class FieldCipher {
  FieldCipher(this.profile);
  final UnlockedProfile profile;
  final _aes = AesGcm.with256bits();
  List<int> _aad(String id, String field, int revision) => utf8.encode(
    jsonEncode([
      'io.github.umichata.tokenlogue.dart',
      1,
      profile.id,
      id,
      field,
      revision,
    ]),
  );
  Future<Uint8List> seal(
    String text,
    String id,
    String field,
    int revision,
  ) async {
    if (profile.disposed) throw StateError('locked');
    final box = await _aes.encrypt(
      utf8.encode(text),
      secretKey: profile.dek,
      aad: _aad(id, field, revision),
    );
    return box.concatenation();
  }

  Future<String> open(
    Uint8List packed,
    String id,
    String field,
    int revision,
  ) async {
    if (profile.disposed) throw StateError('locked');
    final box = SecretBox.fromConcatenation(
      packed,
      nonceLength: 12,
      macLength: 16,
    );
    return utf8.decode(
      await _aes.decrypt(
        box,
        secretKey: profile.dek,
        aad: _aad(id, field, revision),
      ),
    );
  }
}

class ChatRecord {
  const ChatRecord(
    this.id,
    this.title,
    this.service,
    this.model,
    this.free,
    this.draft,
    this.revision,
  );
  final String id, title, model, draft;
  final Service service;
  final bool free;
  final int revision;
}

class ChatStore {
  ChatStore._(this.db, this.crypto);
  final Database db;
  final FieldCipher crypto;
  static Future<String> location() async =>
      '${await getDatabasesPath()}/tokenlogue-dart-v1.db';
  static Future<ChatStore> open(UnlockedProfile profile) async {
    final db = await openDatabase(
      await location(),
      version: 1,
      onConfigure: (db) async {
        await db.execute('PRAGMA foreign_keys=ON');
      },
      onCreate: (db, version) async {
        await db.execute('CREATE TABLE profile(id TEXT PRIMARY KEY NOT NULL)');
        await db.insert('profile', {'id': profile.id});
        await db.execute(
          'CREATE TABLE preferences(name TEXT PRIMARY KEY NOT NULL,value TEXT NOT NULL)',
        );
        await db.execute(
          'CREATE TABLE chats(id TEXT PRIMARY KEY NOT NULL, title BLOB NOT NULL,title_rev INTEGER NOT NULL, provider TEXT NOT NULL CHECK(provider IN ("openrouter","vsegpt")),model TEXT NOT NULL,free INTEGER NOT NULL,created INTEGER NOT NULL,token_limit INTEGER,skip_paid INTEGER NOT NULL DEFAULT 0,connection_rev INTEGER NOT NULL DEFAULT 1)',
        );
        await db.execute(
          'CREATE TABLE drafts(chat TEXT PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,rev INTEGER NOT NULL CHECK(rev>0),body BLOB NOT NULL)',
        );
        await db.execute(
          'CREATE TABLE budgets(chat TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,provider TEXT NOT NULL,currency TEXT NOT NULL,amount TEXT,PRIMARY KEY(chat,provider,currency))',
        );
        await db.execute(
          'CREATE TABLE turns(id TEXT PRIMARY KEY NOT NULL,chat TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,created INTEGER NOT NULL)',
        );
        await db.execute(
          'CREATE TABLE messages(id TEXT PRIMARY KEY NOT NULL,turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,role TEXT NOT NULL CHECK(role IN ("user","assistant")),body BLOB NOT NULL,ordinal INTEGER NOT NULL,UNIQUE(turn_id,role))',
        );
        await db.execute(
          'CREATE TABLE attempts(id TEXT PRIMARY KEY NOT NULL,turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,provider TEXT NOT NULL,currency TEXT NOT NULL,requested_model TEXT NOT NULL,actual_model TEXT,dispatch_ms INTEGER,state TEXT NOT NULL,reserved_tokens INTEGER NOT NULL,reserved_cost TEXT,usage_in INTEGER,usage_out INTEGER,usage_total INTEGER,usage_source TEXT,cost TEXT,cost_source TEXT,snapshot BLOB NOT NULL)',
        );
        await db.execute('CREATE INDEX attempts_time ON attempts(dispatch_ms)');
      },
    );
    final rows = await db.query('profile');
    if (rows.length != 1 || rows.single['id'] != profile.id) {
      await db.close();
      throw StateError('binding');
    }
    return ChatStore._(db, FieldCipher(profile));
  }

  Future<List<ChatRecord>> chats() async {
    final rows = await db.rawQuery(
      'SELECT c.*,d.body AS draft,d.rev AS dr FROM chats c LEFT JOIN drafts d ON d.chat=c.id ORDER BY created DESC,id',
    );
    final list = <ChatRecord>[];
    for (final row in rows) {
      final id = row['id'] as String, rev = row['dr'] as int? ?? 0;
      list.add(
        ChatRecord(
          id,
          await crypto.open(
            row['title'] as Uint8List,
            id,
            'title',
            row['title_rev'] as int,
          ),
          Service.values.byName(row['provider'] as String),
          row['model'] as String,
          row['free'] == 1,
          rev == 0
              ? ''
              : await crypto.open(row['draft'] as Uint8List, id, 'draft', rev),
          rev,
        ),
      );
    }
    return list;
  }

  Future<String> createChat(
    String title,
    Service provider,
    String model,
    bool free,
  ) async {
    if (title.trim().isEmpty ||
        model.isEmpty ||
        (free && provider != Service.openrouter)) {
      throw ArgumentError();
    }
    final id = base64UrlEncode(randomBytes(18));
    final encrypted = await crypto.seal(title, id, 'title', 1);
    await db.insert('chats', {
      'id': id,
      'title': encrypted,
      'title_rev': 1,
      'provider': provider.name,
      'model': model,
      'free': free ? 1 : 0,
      'created': DateTime.now().millisecondsSinceEpoch,
    });
    return id;
  }

  Future<void> rename(String chat, String value) async {
    if (value.trim().isEmpty) throw ArgumentError();
    await db.transaction((tx) async {
      final row = (await tx.query(
        'chats',
        columns: ['title_rev'],
        where: 'id=?',
        whereArgs: [chat],
      )).single;
      final rev = (row['title_rev'] as int) + 1;
      await tx.update(
        'chats',
        {
          'title_rev': rev,
          'title': await crypto.seal(value, chat, 'title', rev),
        },
        where: 'id=?',
        whereArgs: [chat],
      );
    });
  }

  Future<int> saveDraft(String id, String value, int expectedRevision) async =>
      db.transaction((tx) async {
        final old = await tx.query(
          'drafts',
          columns: ['rev'],
          where: 'chat=?',
          whereArgs: [id],
        );
        final rev = old.isEmpty ? 0 : old.single['rev'] as int;
        if (rev != expectedRevision) throw StateError('stale_draft');
        final next = rev + 1;
        await tx.insert('drafts', {
          'chat': id,
          'body': await crypto.seal(value, id, 'draft', next),
          'rev': next,
        }, conflictAlgorithm: ConflictAlgorithm.replace);
        return next;
      });
  Future<void> deleteChat(String id) async {
    await db.delete('chats', where: 'id=?', whereArgs: [id]);
  }
}
