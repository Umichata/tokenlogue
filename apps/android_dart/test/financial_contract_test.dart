import 'package:flutter_test/flutter_test.dart';
import 'package:tokenlogue_dart/domain/amount.dart';
import 'package:tokenlogue_dart/domain/catalogue.dart';
import 'package:tokenlogue_dart/domain/provider.dart';
import 'package:tokenlogue_dart/domain/analytics.dart';
import 'package:tokenlogue_dart/data/transport.dart';

void main() {
  final a = (String s) => Amount.parse(s)!;
  test(
    'prices preserve decimal spelling from JSON and exact 10% threshold',
    () {
      final json = decodeProviderJson(
        '{"price":0.0000000000000001234567890123456789,"s":"1e-3","count":2}',
      );
      expect((json as Map)['price'], '0.0000000000000001234567890123456789');
      expect((a('0.1') + a('2e-1')).toString(), '0.3');
      expect(a('0.00001').times(1000000).toString(), '10');
      expect(encodePayload({'p': a('4e-9')}), '{"p":0.000000004}');
      bool warn(String estimate) => budgetWarning(
        limit: a('1'),
        used: a('0'),
        reserve: a('0.2'),
        estimate: a(estimate),
      );
      expect(warn('0.699999999999999999'), isFalse);
      expect(warn('0.7'), isTrue);
      expect(warn('1.1'), isTrue);
      expect(
        budgetWarning(
          limit: a('1'),
          used: a('0'),
          reserve: a('0'),
          estimate: null,
        ),
        isTrue,
      );
    },
  );
  test(
    'VSEGPT text catalogue has unknown RUB price, OpenRouter free must have all zero rates',
    () {
      final row = {
        'id': 'openai/example:free',
        'name': 'Example',
        'context_length': 4096,
        'architecture': {
          'input_modalities': ['text'],
          'output_modalities': ['text'],
        },
        'pricing': {'prompt': '0', 'completion': '0', 'request': '0'},
      };
      expect(catalogue(Service.openrouter, [row]).single.free, isTrue);
      expect(
        catalogue(Service.openrouter, [
          {
            ...row,
            'pricing_overrides': [
              {
                'pricing': {'request': '0.0001'},
              },
            ],
          },
        ]).single.free,
        isFalse,
      );
      expect(
        catalogue(Service.openrouter, [
          {
            ...row,
            'pricing': {'prompt': '0', 'completion': '0', 'unknown_rate': '0'},
          },
        ]),
        isEmpty,
      );
      expect(catalogue(Service.vsegpt, [row]).single.quote(5, 20), isNull);
      expect(
        catalogue(Service.vsegpt, [
          {...row, 'id': 'image/nope'},
        ]),
        isEmpty,
      );
    },
  );
  test(
    'identical model names, undated attempts and currencies stay separate',
    () {
      final now = DateTime(2026, 11, 19, 14);
      final rows = [
        for (final provider in Service.values)
          {
            'provider': provider.name,
            'currency': provider.currency,
            'requested_model': 'same',
            'dispatch_ms': now.millisecondsSinceEpoch,
            'cost': provider == Service.vsegpt ? null : '1e-8',
            'cost_source': provider == Service.vsegpt ? 'unknown' : 'api',
            'usage_total': null,
          },
        {
          'provider': 'openrouter',
          'currency': 'USD',
          'requested_model': 'same',
          'dispatch_ms': null,
          'usage_total': 1,
          'usage_source': 'api',
          'cost': '1',
          'cost_source': 'api',
        },
      ];
      final all = daily(
        rows,
        provider: 'all',
        model: 'all',
        days: null,
        now: now,
        money: true,
      );
      expect(all.length, 3);
      expect(all.where((x) => x.currency == 'RUB').single.unknownCost, 1);
      expect(all.where((x) => x.date.isEmpty).single.attempts, 1);
      expect(
        daily(
          rows,
          provider: 'all',
          model: 'openrouter/same',
          days: 7,
          now: now,
          money: true,
        ).single.confirmed,
        a('1e-8'),
      );
    },
  );
}
