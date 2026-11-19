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
    duringSend?.call();
    if (failure != null) throw failure!;
    return {
      'id': 'fixture',
      'model': 'test/free:free',
      'choices': [
        {
          'message': {'role': 'assistant', 'content': 'neutral answer'},
          'finish_reason': 'stop',
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
}
