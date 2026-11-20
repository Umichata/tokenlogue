import 'dart:convert';
import 'dart:typed_data';
import 'package:sqflite/sqflite.dart';
import '../domain/provider.dart';
import '../domain/amount.dart';
import '../domain/catalogue.dart';
import '../domain/request_plan.dart';
import '../domain/usage.dart';
import 'chat_store.dart';
import 'vault.dart';

String newId() => base64UrlEncode(randomBytes(18));
typedef JournalRow = Map<String, Object?>;
typedef BudgetTotal = ({
  int used,
  int reserved,
  Amount spent,
  Amount held,
  bool blocked,
});

Future<void> schema2(DatabaseExecutor db) async {
  await db.execute(
    'ALTER TABLE chats ADD COLUMN response_limit INTEGER NOT NULL DEFAULT 1024 CHECK(response_limit>=16)',
  );
  await db.execute('ALTER TABLE chats ADD COLUMN price TEXT');
  await db.execute('ALTER TABLE attempts ADD COLUMN draft_revision INTEGER');
  await db.execute('ALTER TABLE attempts ADD COLUMN error TEXT');
  await db.execute(
    'CREATE UNIQUE INDEX one_live_attempt_per_turn ON attempts(turn_id) WHERE state="pending"',
  );
}

/// Earlier builds stored both localized default titles encrypted. A rename
/// incremented title_rev even if the user chose the same visible title.
Future<void> schema4(Database db, FieldCipher cipher) async {
  final identity = await db.query('profile', columns: ['id']);
  if (identity.length != 1 || identity.single['id'] != cipher.profile.id) {
    throw StateError('profile_binding');
  }
  await db.execute('ALTER TABLE attempts ADD COLUMN finish_reason TEXT');
  await db.execute(
    'ALTER TABLE chats ADD COLUMN placeholder_title INTEGER NOT NULL DEFAULT 0',
  );
  final candidates = await db.rawQuery(
    "SELECT c.id,c.title FROM chats c WHERE c.title_rev=1 AND NOT EXISTS "
    "(SELECT 1 FROM turns t JOIN messages m ON m.turn_id=t.id WHERE t.chat=c.id AND m.role='assistant')",
  );
  for (final row in candidates) {
    final id = row['id'] as String;
    final title = await cipher.open(row['title'] as Uint8List, id, 'title', 1);
    if (title == 'New chat' || title == 'Новый чат') {
      await db.update(
        'chats',
        {'placeholder_title': 1},
        where: 'id=?',
        whereArgs: [id],
      );
    }
  }
}

String messageField(Object? chat, Object? turn, Object? role) =>
    jsonEncode(['message', chat, turn, role]);
String dispatchField(
  Object? chat,
  Object? turn,
  Object? provider,
  Object? currency,
  Object? model,
) => jsonEncode(['dispatch', chat, turn, provider, currency, model]);

/// Runs inside sqflite's upgrade transaction. Only ciphertext is written.
/// A failure authenticating any old row aborts the entire migration.
Future<void> bindJournalToChat(Database db, FieldCipher cipher) async {
  final identity = await db.query('profile', columns: ['id']);
  if (identity.length != 1 ||
      identity.single['id'] != cipher.profile.id ||
      (await db.rawQuery('PRAGMA foreign_key_check')).isNotEmpty) {
    throw StateError('profile_binding');
  }
  for (final messages in [true, false]) {
    final table = messages ? 'messages' : 'attempts',
        field = messages ? 'body' : 'snapshot';
    var after = 0;
    while (true) {
      final rows = await db.rawQuery(
        'SELECT r.*,r.rowid AS cursor,t.chat FROM $table r JOIN turns t ON t.id=r.turn_id WHERE r.rowid>? ORDER BY r.rowid LIMIT 64',
        [after],
      );
      if (rows.isEmpty) break;
      for (final row in rows) {
        final id = row['id'] as String,
            turn = row['turn_id'],
            chat = row['chat'];
        final old = messages ? '$turn:${row["role"]}' : 'dispatch';
        final bound = messages
            ? messageField(chat, turn, row['role'])
            : dispatchField(
                chat,
                turn,
                row['provider'],
                row['currency'],
                row['requested_model'],
              );
        final value = await cipher.open(row[field] as Uint8List, id, old, 1);
        await db.update(
          table,
          {field: await cipher.seal(value, id, bound, 2)},
          where: 'id=?',
          whereArgs: [id],
        );
      }
      after = rows.last['cursor'] as int;
    }
  }
}

extension Journal on ChatStore {
  Future<String?> preference(String name) async =>
      (await db.query(
            'preferences',
            columns: ['value'],
            where: 'name=?',
            whereArgs: [name],
          )).firstOrNull?['value']
          as String?;
  Future<void> setPreference(String name, String value) async {
    await db.insert('preferences', {
      'name': name,
      'value': value,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<List<JournalRow>> journal({String? chat}) => db.rawQuery(
    'SELECT a.id,a.turn_id,a.provider,a.currency,a.requested_model,a.actual_model,a.finish_reason,a.dispatch_ms,a.state,a.reserved_tokens,a.reserved_cost,a.usage_in,a.usage_out,a.usage_total,a.usage_source,a.cost,a.cost_source,a.draft_revision,a.error,t.chat FROM attempts a JOIN turns t ON a.turn_id=t.id ${chat == null ? '' : 'WHERE t.chat=?'} ORDER BY a.dispatch_ms,a.rowid',
    chat == null ? [] : [chat],
  );
  Future<List<Map<String, String>>> dispatchSnapshot(JournalRow attempt) async {
    final snapshot = (await db.query(
      'attempts',
      columns: ['snapshot'],
      where: 'id=? AND turn_id=?',
      whereArgs: [attempt['id'], attempt['turn_id']],
    )).single;
    final text = await crypto.open(
      snapshot['snapshot'] as Uint8List,
      attempt['id'] as String,
      dispatchField(
        attempt['chat'],
        attempt['turn_id'],
        attempt['provider'],
        attempt['currency'],
        attempt['requested_model'],
      ),
      2,
    );
    final raw = jsonDecode(text) as List;
    return [for (final m in raw) Map<String, String>.from(m as Map)];
  }

  Future<JournalRow> settings(String chat) async =>
      (await db.query('chats', where: 'id=?', whereArgs: [chat])).single;
  Future<Amount?> limitFor(String chat, Service s) async => Amount.parse(
    (await db.query(
      'budgets',
      where: 'chat=? AND provider=? AND currency=?',
      whereArgs: [chat, s.name, s.currency],
    )).firstOrNull?['amount'],
  );
  Future<List<({String turn, String role, String body})>> history(
    String chat,
  ) async {
    final rows = await db.rawQuery(
      'SELECT m.* FROM messages m JOIN turns t ON t.id=m.turn_id WHERE t.chat=? ORDER BY t.created,t.rowid,m.ordinal',
      [chat],
    );
    return [
      for (final m in rows)
        (
          turn: m['turn_id'] as String,
          role: m['role'] as String,
          body: await crypto.open(
            m['body'] as Uint8List,
            m['id'] as String,
            messageField(chat, m['turn_id'], m['role']),
            2,
          ),
        ),
    ];
  }

  Future<void> configure({
    String? existing,
    required String id,
    required String title,
    required ModelChoice model,
    required int tokens,
    required int output,
    required Amount? budget,
    required bool skip,
    required bool reconnect,
    bool placeholderTitle = false,
  }) async {
    if (tokens < 16 ||
        output < 16 ||
        output > tokens ||
        !model.free && (budget == null || budget.coefficient.sign <= 0)) {
      throw const PlanRejected('service.error.limits');
    }
    final encrypted = existing == null
        ? await crypto.seal(title, id, 'title', 1)
        : null;
    await db.transaction((tx) async {
      final state = await tx.rawQuery(
        'SELECT a.state FROM attempts a JOIN turns t ON a.turn_id=t.id WHERE t.chat=? AND a.state IN ("pending","unknown","unknownCost") LIMIT 1',
        [id],
      );
      if (state.isNotEmpty && reconnect) {
        throw const PlanRejected('service.previous_unknown');
      }
      final common = {
        'provider': model.service.name,
        'model': model.id,
        'price': jsonEncode(model.toJson()),
        'free': model.free ? 1 : 0,
        'token_limit': tokens,
        'response_limit': output,
        'skip_paid': reconnect
            ? 0
            : skip
            ? 1
            : 0,
      };
      if (existing == null) {
        await tx.insert('chats', {
          'id': id,
          'title': encrypted,
          'placeholder_title': placeholderTitle ? 1 : 0,
          'title_rev': 1,
          'created': DateTime.now().millisecondsSinceEpoch,
          ...common,
        });
      } else {
        final prev = (await tx.query(
          'chats',
          columns: ['connection_rev'],
          where: 'id=?',
          whereArgs: [existing],
        )).single;
        await tx.update(
          'chats',
          {...common, 'connection_rev': (prev['connection_rev'] as int) + 1},
          where: 'id=?',
          whereArgs: [existing],
        );
      }
      if (budget != null && !model.free) {
        await tx.insert('budgets', {
          'chat': id,
          'provider': model.service.name,
          'currency': model.service.currency,
          'amount': budget.toString(),
        }, conflictAlgorithm: ConflictAlgorithm.replace);
      }
    });
  }

  Future<void> confirmPrice(
    String chat,
    int connectionRevision,
    ModelChoice price,
  ) async {
    final count = await db.update(
      'chats',
      {
        'price': jsonEncode(price.toJson()),
        'connection_rev': connectionRevision + 1,
      },
      where: 'id=? AND connection_rev=? AND provider=? AND model=?',
      whereArgs: [chat, connectionRevision, price.service.name, price.id],
    );
    if (count != 1) throw const PlanRejected('service.error.price_confirm');
  }

  Future<({String attempt, String turn})> reserve({
    required String chat,
    required String text,
    required int rev,
    required int connection,
    required ModelChoice model,
    required RequestPlan plan,
    required List<JournalRow> observed,
    String? retryTurn,
  }) async {
    final turn = retryTurn ?? newId(),
        attempt = newId(),
        message = newId(),
        now = DateTime.now().millisecondsSinceEpoch;
    final msg = await crypto.seal(
      text,
      message,
      messageField(chat, turn, 'user'),
      2,
    );
    final snapshot = await crypto.seal(
      jsonEncode(plan.messages),
      attempt,
      dispatchField(
        chat,
        turn,
        model.service.name,
        model.service.currency,
        model.id,
      ),
      2,
    );
    await db.transaction((tx) async {
      final c = (await tx.query(
        'chats',
        where: 'id=?',
        whereArgs: [chat],
      )).single;
      final dr = (await tx.query(
        'drafts',
        columns: ['rev'],
        where: 'chat=?',
        whereArgs: [chat],
      )).firstOrNull;
      if (c['connection_rev'] != connection ||
          c['provider'] != model.service.name ||
          c['model'] != model.id ||
          (retryTurn == null && (dr?['rev'] ?? 0) != rev)) {
        throw const PlanRejected('service.error.retry');
      }
      final actual = await tx.rawQuery(
        'SELECT a.id,a.state FROM attempts a JOIN turns t ON a.turn_id=t.id WHERE t.chat=? ORDER BY a.dispatch_ms,a.rowid',
        [chat],
      );
      if (actual.length != observed.length ||
          actual.asMap().entries.any(
            (e) =>
                e.value['id'] != observed[e.key]['id'] ||
                e.value['state'] != observed[e.key]['state'],
          ) ||
          actual.any(
            (r) => ['pending', 'unknown', 'unknownCost'].contains(r['state']),
          )) {
        throw const PlanRejected('service.previous_unknown');
      }
      if (retryTurn == null) {
        await tx.insert('turns', {'id': turn, 'chat': chat, 'created': now});
        await tx.insert('messages', {
          'id': message,
          'turn_id': turn,
          'role': 'user',
          'ordinal': 0,
          'body': msg,
        });
      } else {
        final last = observed.where((r) => r['turn_id'] == turn).lastOrNull;
        if (last == null ||
            last['state'] != 'failed' ||
            last['requested_model'] != model.id ||
            last['provider'] != model.service.name) {
          throw const PlanRejected('service.error.retry');
        }
      }
      await tx.insert('attempts', {
        'id': attempt,
        'turn_id': turn,
        'provider': model.service.name,
        'currency': model.service.currency,
        'requested_model': model.id,
        'dispatch_ms': now,
        'state': 'pending',
        'reserved_tokens': plan.prompt + plan.completion,
        'reserved_cost': plan.reservationAmount.toString(),
        'draft_revision': retryTurn == null ? rev : null,
        'snapshot': snapshot,
      });
    });
    return (attempt: attempt, turn: turn);
  }

  Future<void> fail(
    String attempt,
    String label,
    bool unknown, {
    ReportedUsage usage = const ReportedUsage(),
  }) async {
    await db.update(
      'attempts',
      {
        'state': unknown ? 'unknown' : 'failed',
        'error': label,
        'usage_in': usage.input,
        'usage_out': usage.output,
        'usage_total': usage.total,
        'usage_source': usage.hasTokens ? 'api' : 'unknown',
        'cost': usage.cost?.toString(),
        'cost_source': usage.cost == null ? 'unknown' : 'api',
        if (!unknown || usage.total != null) 'reserved_tokens': 0,
        if (!unknown || usage.cost != null) 'reserved_cost': '0',
      },
      where: 'id=? AND state="pending"',
      whereArgs: [attempt],
    );
  }

  Future<void> releaseUnknown(String chat, String id) async {
    await db.rawUpdate(
      'UPDATE attempts SET state="released",reserved_tokens=0,reserved_cost="0" WHERE id=? AND state IN ("unknown","unknownCost") AND turn_id IN (SELECT id FROM turns WHERE chat=?)',
      [id, chat],
    );
  }

  Future<void> settle({
    required String chat,
    required String turn,
    required String attempt,
    required String answer,
    String? firstPrompt,
    String? finishReason,
    required String actual,
    required int? input,
    required int? output,
    required int? total,
    required Amount? cost,
    required String costSource,
    required String usageSource,
    required bool unknown,
  }) async {
    final id = newId(),
        encrypted = await crypto.seal(
          answer,
          id,
          messageField(chat, turn, 'assistant'),
          2,
        );
    await db.transaction((tx) async {
      final record = (await tx.query(
        'attempts',
        where: 'id=? AND turn_id=? AND state="pending"',
        whereArgs: [attempt, turn],
      )).firstOrNull;
      if (record == null) return;
      await tx.insert('messages', {
        'id': id,
        'turn_id': turn,
        'ordinal': 1,
        'role': 'assistant',
        'body': encrypted,
      });
      await tx.update(
        'attempts',
        {
          'actual_model': actual,
          'finish_reason': finishReason,
          'state': unknown ? 'unknownCost' : 'sent',
          'usage_in': input,
          'usage_out': output,
          'usage_total': total,
          'usage_source': usageSource,
          'cost': cost?.toString(),
          'cost_source': costSource,
          'reserved_tokens': total == null ? record['reserved_tokens'] : 0,
          'reserved_cost': cost == null ? record['reserved_cost'] : '0',
        },
        where: 'id=?',
        whereArgs: [attempt],
      );
      if (firstPrompt != null) {
        final placeholder = (await tx.query(
          'chats',
          columns: ['title_rev'],
          where: 'id=? AND placeholder_title=1',
          whereArgs: [chat],
        )).firstOrNull;
        if (placeholder != null) {
          final title = String.fromCharCodes(
            firstPrompt.trim().replaceAll(RegExp(r'\s+'), ' ').runes.take(60),
          ).trimRight();
          if (title.isNotEmpty) {
            final rev = (placeholder['title_rev'] as int) + 1;
            await tx.update(
              'chats',
              {
                'title': await crypto.seal(title, chat, 'title', rev),
                'title_rev': rev,
                'placeholder_title': 0,
              },
              where: 'id=?',
              whereArgs: [chat],
            );
          }
        }
      }
      if (record['draft_revision'] != null) {
        final rev = (record['draft_revision'] as int) + 1;
        // Keep monotonic revisions and compare before clearing an edited draft.
        await tx.update(
          'drafts',
          {'body': await crypto.seal('', chat, 'draft', rev), 'rev': rev},
          where: 'chat=? AND rev=?',
          whereArgs: [chat, record['draft_revision']],
        );
      }
    });
  }
}

BudgetTotal totals(List<JournalRow> rows, Service service) {
  var used = 0,
      reserved = 0,
      spent = Amount.zero,
      held = Amount.zero,
      blocked = false;
  for (final a in rows) {
    used += a['usage_total'] as int? ?? 0;
    reserved += a['reserved_tokens'] as int;
    if (['unknown', 'unknownCost', 'pending'].contains(a['state'])) {
      blocked = true;
    }
    if (a['provider'] == service.name && a['currency'] == service.currency) {
      spent += Amount.parse(a['cost']) ?? Amount.zero;
      held += Amount.parse(a['reserved_cost']) ?? Amount.zero;
    }
  }
  return (
    used: used,
    reserved: reserved,
    spent: spent,
    held: held,
    blocked: blocked,
  );
}
