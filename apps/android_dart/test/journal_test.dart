import 'dart:io';
import 'package:cryptography/cryptography.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:tokenlogue_dart/data/chat_service.dart';
import 'package:tokenlogue_dart/data/chat_store.dart';
import 'package:tokenlogue_dart/data/journal.dart';
import 'package:tokenlogue_dart/data/providers.dart';
import 'package:tokenlogue_dart/data/transport.dart';
import 'package:tokenlogue_dart/data/vault.dart';
import 'package:tokenlogue_dart/domain/catalogue.dart';
import 'package:tokenlogue_dart/domain/provider.dart';
import 'package:tokenlogue_dart/domain/request_plan.dart';

class FixtureTransport implements Transport {
  int calls = 0;
  String finishReason = 'stop';
  final contexts = <Object?>[];
  ApiFailure? failure;
  void Function()? duringSend;
  @override
  Future<Payload> request(
    Service service,
    String key,
    Resource resource, [
    Payload? body,
  ]) async {
    expect(Service.detect(key), service);
    if (resource != Resource.completion) {
      throw StateError('Unexpected network request');
    }
    expect(service, Service.openrouter);
    expect(body!['model'], 'openrouter/free');
    expect(
      encodePayload(body['provider']['max_price']),
      '{"prompt":0,"completion":0,"request":0}',
    );
    calls++;
    contexts.add(body['messages']);
    duringSend?.call();
    if (failure != null) throw failure!;
    return {
      'id': 'fixture',
      'model': 'test/free:free',
      'choices': [
        {
          'message': {'role': 'assistant', 'content': 'neutral answer'},
          'finish_reason': finishReason,
        },
      ],
      'usage': {
        'prompt_tokens': 12,
        'completion_tokens': 4,
        'total_tokens': 16,
        'cost': '0',
      },
    };
  }
}

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  late Directory temp;
  late ChatStore store;
  late FixtureTransport http;
  late ChatService service;
  UnlockedProfile profile() =>
      UnlockedProfile('unit-profile', SecretKey(List.filled(32, 7)), {
        'openrouter': {'key': 'sk-or-v1-unit-fixture'},
      });
  setUp(() async {
    temp = await Directory.systemTemp.createTemp('dart-chat-contract-');
    await databaseFactory.setDatabasesPath(temp.path);
    store = await ChatStore.open(profile());
    http = FixtureTransport();
    service = ChatService(store, ProviderApi(http));
    await store.configure(
      id: 'one',
      title: '旅行',
      model: ModelChoice.router,
      tokens: 8192,
      output: 128,
      budget: null,
      skip: false,
      reconnect: false,
    );
    await store.saveDraft('one', 'neutral synthetic message', 0);
  });
  tearDown(() async {
    await store.db.close();
    await temp.delete(recursive: true);
  });
  test(
    'first saved reply names only a placeholder and keeps length and accounting through reopen',
    () async {
      await store.configure(
        id: 'two',
        title: 'New chat',
        placeholderTitle: true,
        model: ModelChoice.router,
        tokens: 8192,
        output: 128,
        budget: null,
        skip: false,
        reconnect: false,
      );
      final long = List.filled(65, '🚆').join();
      await store.saveDraft('two', '  Trip  \n  $long ', 0);
      http.finishReason = 'length';
      final chat = (await store.chats()).firstWhere((c) => c.id == 'two');
      await service.dispatch(await service.preview(chat), confirmed: false);
      await store.db.close();
      store = await ChatStore.open(profile());
      final updated = (await store.chats()).firstWhere((c) => c.id == 'two');
      expect(updated.title, 'Trip ${List.filled(55, '🚆').join()}');
      final row = (await store.journal(chat: 'two')).single;
      expect(
        [
          row['finish_reason'],
          row['actual_model'],
          row['usage_in'],
          row['usage_out'],
          row['usage_total'],
          row['cost'],
        ],
        ['length', 'test/free:free', 12, 4, 16, '0'],
      );
      await store.configure(
        id: 'manual',
        title: 'New chat',
        placeholderTitle: true,
        model: ModelChoice.router,
        tokens: 8192,
        output: 128,
        budget: null,
        skip: false,
        reconnect: false,
      );
      await store.saveDraft('manual', 'Keep the manual title', 0);
      await store.rename('manual', 'New chat');
      service = ChatService(store, ProviderApi(http));
      await service.dispatch(
        await service.preview(
          (await store.chats()).firstWhere((c) => c.id == 'manual'),
        ),
        confirmed: false,
      );
      expect(
        (await store.chats()).firstWhere((c) => c.id == 'manual').title,
        'New chat',
      );
    },
  );
  test(
    'post-dispatch timeout retains reserve and IDs across a cold open until explicitly released',
    () async {
      http.failure = const ApiFailure('catalog.error.timeout', uncertain: true);
      final initial = (await store.chats()).single;
      await expectLater(
        service.dispatch(await service.preview(initial), confirmed: false),
        throwsA(isA<ApiFailure>()),
      );
      final before = (await store.journal()).single;
      await store.db.close();
      store = await ChatStore.open(profile());
      service = ChatService(store, ProviderApi(http));
      final after = (await store.journal()).single;
      expect(after, before);
      expect(after['reserved_tokens'], greaterThan(0));
      expect(after['state'], 'unknown');
      expect(http.calls, 1);
      await expectLater(
        service.preview((await store.chats()).single),
        throwsA(isA<PlanRejected>()),
      );
      await store.releaseUnknown('different', after['id'] as String);
      expect((await store.journal()).single, before);
      await store.releaseUnknown('one', after['id'] as String);
      expect((await store.journal()).single['state'], 'released');
      expect((await store.chats()).single.draft, initial.draft);
      expect(http.calls, 1);
    },
  );
  test(
    'one preview cannot send twice and a later draft revision survives settlement',
    () async {
      final q = await service.preview((await store.chats()).single);
      late Future<int> change;
      http.duringSend = () {
        change = store.saveDraft('one', '  replacement 🌲\n', 1);
      };
      await service.dispatch(q, confirmed: false);
      await change;
      await expectLater(
        service.dispatch(q, confirmed: false),
        throwsA(isA<PlanRejected>()),
      );
      expect((await store.chats()).single.draft, '  replacement 🌲\n');
      expect((await store.history('one')).length, 2);
      expect((await store.journal()).single['usage_total'], 16);
      expect(http.calls, 1);
    },
  );
  test(
    'a crash after reserving is recovered as unknown without another transport call',
    () async {
      final q = await service.preview((await store.chats()).single);
      await store.reserve(
        chat: 'one',
        text: q.text,
        rev: q.rev,
        connection: q.version,
        model: q.model,
        plan: q.plan,
        observed: q.rows,
      );
      await store.db.close();
      store = await ChatStore.open(profile());
      expect((await store.journal()).single['state'], 'unknown');
      expect(http.calls, 0);
    },
  );
  test(
    'moving a turn between chats fails authentication of messages and dispatch context',
    () async {
      final prepared = await service.preview((await store.chats()).single);
      await service.dispatch(prepared, confirmed: false);
      await store.configure(
        id: 'two',
        title: 'Other',
        model: ModelChoice.router,
        tokens: 4096,
        output: 32,
        budget: null,
        skip: false,
        reconnect: false,
      );
      final attempt = (await store.journal()).single;
      await store.db.update(
        'turns',
        {'chat': 'two'},
        where: 'id=?',
        whereArgs: [attempt['turn_id']],
      );
      await expectLater(
        store.history('two'),
        throwsA(isA<SecretBoxAuthenticationError>()),
      );
      await expectLater(
        store.dispatchSnapshot((await store.journal(chat: 'two')).single),
        throwsA(isA<SecretBoxAuthenticationError>()),
      );
    },
  );
  test(
    'explicit retry uses the original messages and preserves the next draft',
    () async {
      final initial = (await store.chats()).single;
      http.failure = const ApiFailure('service.error.network');
      await expectLater(
        service.dispatch(await service.preview(initial), confirmed: false),
        throwsA(isA<ApiFailure>()),
      );
      final failed = (await store.journal()).single;
      expect(failed['state'], 'failed');
      expect(failed['reserved_tokens'], 0);
      await store.saveDraft(
        'one',
        '  next unsent message 🌱  ',
        initial.revision,
      );
      http.failure = null;
      final next = (await store.chats()).single;
      final retry = await service.preview(
        next,
        retry: failed['turn_id'] as String,
      );
      await service.dispatch(retry, confirmed: false);
      final journal = await store.journal(),
          history = await store.history('one');
      expect(journal.map((a) => a['turn_id']).toSet(), {failed['turn_id']});
      expect(journal.map((a) => a['state']), ['failed', 'sent']);
      expect(history.map((m) => m.role), ['user', 'assistant']);
      expect(history.first.body, initial.draft);
      expect((await store.chats()).single.draft, next.draft);
      expect(http.calls, 2);
      expect(http.contexts.first, http.contexts.last);
    },
  );
}
