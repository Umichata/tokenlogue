import 'dart:async';
import 'dart:convert';
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
import 'package:tokenlogue_dart/domain/amount.dart';
import 'package:tokenlogue_dart/domain/catalogue.dart';
import 'package:tokenlogue_dart/domain/provider.dart';
import 'package:tokenlogue_dart/domain/request_plan.dart';

class CatalogueFixture implements Transport {
  String price = '0.0001';
  bool absent = false;
  ApiFailure? modelError;
  final calls = <Resource>[];
  Completer<void>? barrier;
  Payload get row => {
    'id': 'openai/unit',
    'name': 'Unit',
    'context_length': 8192,
    'architecture': {
      'input_modalities': ['text'],
      'output_modalities': ['text'],
    },
    'pricing': {'prompt': price, 'completion': price},
  };
  @override
  Future<Payload> request(
    Service service,
    String key,
    Resource resource, [
    Payload? body,
  ]) async {
    expect(Service.detect(key), service);
    calls.add(resource);
    if (resource == Resource.models) {
      if (barrier != null) await barrier!.future;
      if (modelError != null) throw modelError!;
      return {
        'data': absent ? [] : [row],
      };
    }
    if (resource == Resource.key) {
      return {
        'data': {'limit_remaining': null},
      };
    }
    if (resource == Resource.completion) {
      if (service == Service.vsegpt) {
        expect(body, isNot(contains('provider')));
        expect(body, isNot(contains('max_completion_tokens')));
        expect(body, contains('max_tokens'));
      }
      return {
        'id': 'unit',
        'model': 'openai/unit',
        'choices': [
          {
            'message': {'role': 'assistant', 'content': 'reply'},
            'finish_reason': 'stop',
          },
        ],
        'usage': {
          'prompt_tokens': 15,
          'completion_tokens': 4,
          'total_tokens': 19,
          'cost': '8.19',
        },
      };
    }
    throw StateError('unexpected request');
  }
}

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  late Directory dir;
  late ChatStore store;
  late CatalogueFixture api;
  late ChatService service;
  setUp(() async {
    dir = await Directory.systemTemp.createTemp('dart-paid-test-');
    await databaseFactory.setDatabasesPath(dir.path);
    store = await ChatStore.open(
      UnlockedProfile('unit', SecretKey(List.filled(32, 12)), {
        'openrouter': {'key': 'sk-or-v1-testing'},
        'vsegpt': {'key': 'sk-or-visLOCAL_TEST'},
      }),
    );
    api = CatalogueFixture();
    service = ChatService(store, ProviderApi(api));
  });
  tearDown(() async {
    await store.db.close();
    await dir.delete(recursive: true);
  });
  Future<ChatRecord> setup(Service s) async {
    final model = catalogue(s, [api.row]).single;
    await store.configure(
      id: 'one',
      title: 'work',
      model: model,
      tokens: 8192,
      output: 64,
      budget: Amount.parse('5'),
      skip: false,
      reconnect: false,
    );
    await store.saveDraft('one', '  input 🌱 ', 0);
    return (await store.chats()).single;
  }

  test(
    'catalogue failure differs from missing model and preserves confirmed price after repreview failure',
    () async {
      final c = await setup(Service.openrouter);
      api.price = '0.0002';
      late ChangedPrice change;
      try {
        await service.preview(c);
        fail('price consent required');
      } on ChangedPrice catch (e) {
        change = e;
      }
      expect(
        (jsonDecode((await store.settings(c.id))['price'] as String)['rates']
                as List)
            .first['prompt'],
        '0.0001',
      );
      await store.confirmPrice(change.chat, change.version, change.current);
      api.modelError = const ApiFailure('catalog.error.timeout');
      await expectLater(
        service.preview(c),
        throwsA(
          isA<ApiFailure>().having(
            (e) => e.label,
            'category',
            'catalog.error.timeout',
          ),
        ),
      );
      api.modelError = null;
      api.absent = true;
      await expectLater(
        service.preview(c),
        throwsA(
          isA<PlanRejected>().having(
            (e) => e.message,
            'category',
            'service.error.model_missing',
          ),
        ),
      );
      expect(
        (jsonDecode((await store.settings(c.id))['price'] as String)['rates']
                as List)
            .first['prompt'],
        '0.0002',
      );
      expect((await store.chats()).single.draft, c.draft);
      expect(await store.journal(), isEmpty);
      expect(api.calls, isNot(contains(Resource.completion)));
    },
  );
  test(
    'navigation during delayed preview and replacement key invalidate paid consent before transport',
    () async {
      final c = await setup(Service.openrouter);
      api.barrier = Completer();
      final pending = service.preview(c);
      while (!api.calls.contains(Resource.models)) {
        await Future<void>.delayed(const Duration(milliseconds: 2));
      }
      service.invalidate();
      api.barrier!.complete();
      await expectLater(pending, throwsA(isA<PlanRejected>()));
      final plan = await service.preview(c);
      store.crypto.profile.credentials['openrouter'] = {
        'key': 'sk-or-v1-replacement',
      };
      await expectLater(
        service.dispatch(plan, confirmed: true),
        throwsA(isA<PlanRejected>()),
      );
      expect(await store.journal(), isEmpty);
    },
  );
  test(
    'changed paid pricing after dialog does not dispatch; no-consent cannot submit',
    () async {
      final c = await setup(Service.openrouter);
      await expectLater(
        service.dispatch(await service.preview(c), confirmed: false),
        throwsA(isA<PlanRejected>()),
      );
      final plan = await service.preview(c);
      api.price = '0.1';
      await expectLater(
        service.dispatch(plan, confirmed: true),
        throwsA(isA<ChangedPrice>()),
      );
      expect(api.calls, isNot(contains(Resource.completion)));
      expect(await store.journal(), isEmpty);
    },
  );
  test(
    'unknown VSEGPT price reserves remaining RUB, API cost in unspecified units never becomes confirmed RUB',
    () async {
      final c = await setup(Service.vsegpt), q = await service.preview(c);
      expect(q.plan.reserve, isNull);
      expect(q.plan.reservationAmount, Amount.parse('5'));
      expect(q.plan.warning, isTrue);
      await service.dispatch(q, confirmed: true);
      final a = (await store.journal()).single;
      expect(a['provider'], 'vsegpt');
      expect(a['currency'], 'RUB');
      expect(a['cost'], isNull);
      expect(a['state'], 'unknownCost');
      expect(a['reserved_cost'], '5');
      expect(a['usage_total'], 19);
      expect(api.calls.where((r) => r == Resource.completion), hasLength(1));
    },
  );
}
