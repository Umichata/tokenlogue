import 'dart:async';
import 'package:cryptography/cryptography.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tokenlogue_dart/data/providers.dart';
import 'package:tokenlogue_dart/data/transport.dart';
import 'package:tokenlogue_dart/data/vault.dart';
import 'package:tokenlogue_dart/domain/provider.dart';
import 'package:tokenlogue_dart/presentation/provider_page.dart';

class DelayedProvider implements Transport {
  final pending = <Completer<Payload>>[];
  @override
  Future<Payload> request(
    Service s,
    String key,
    Resource resource, [
    Payload? body,
  ]) {
    expect(Service.detect(key), s);
    expect(resource, isNot(Resource.completion));
    final c = Completer<Payload>();
    pending.add(c);
    return c.future;
  }
}

void main() {
  test(
    'late balance from a replaced credential never replaces a current VSEGPT balance',
    () async {
      final transport = DelayedProvider(), api = ProviderApi(transport);
      final profile = UnlockedProfile('unit', SecretKey(List.filled(32, 4)), {
        'vsegpt': {'key': 'sk-or-vis-unit-A'},
      });
      final state = AccountState(profile, api);
      final first = state.refresh(Service.vsegpt);
      profile.credentials['vsegpt'] = {'key': 'sk-or-vv-unit-B'};
      state.changed(Service.vsegpt);
      final second = state.refresh(Service.vsegpt);
      transport.pending[1].complete({
        'status': 'ok',
        'data': {
          'credits': '-0.12',
          'subscription_status': 'ok',
          'user_status': 0,
        },
      });
      await second;
      transport.pending[0].complete({
        'status': 'ok',
        'data': {
          'credits': '903.1',
          'subscription_status': 'ok',
          'user_status': 0,
        },
      });
      await first;
      expect(state.values[Service.vsegpt]?.amount, '-0.12');
      final refresh = state.refresh(Service.vsegpt);
      transport.pending.last.completeError(
        const ApiFailure('catalog.error.timeout'),
      );
      await refresh;
      expect(state.values[Service.vsegpt]?.amount, '-0.12');
      expect(state.stale, contains(Service.vsegpt));
      state.dispose();
      profile.dispose();
    },
  );
  test(
    'indeterminate key checks preserve their cause and only VSEGPT permits explicit unverified save',
    () async {
      for (final service in Service.values) {
        final transport = DelayedProvider(), api = ProviderApi(transport);
        final key = service == Service.vsegpt
            ? 'sk-or-vis-unit'
            : 'sk-or-v1-unit';
        for (final (cause, expected, maySave) in [
          ('catalog.error.auth', KeyStatus.invalid, false),
          ('catalog.error.network', KeyStatus.network, true),
          ('catalog.error.tls', KeyStatus.tls, true),
          ('catalog.error.timeout', KeyStatus.timeout, true),
          ('catalog.error.rate', KeyStatus.limited, true),
          ('catalog.error.schema', KeyStatus.malformed, false),
          ('catalog.error.http', KeyStatus.unavailable, true),
        ]) {
          final check = api.check(service, key);
          transport.pending.last.completeError(ApiFailure(cause));
          final result = await check;
          expect(result, expected);
          expect(
            result.maySaveUnverified(service),
            maySave && service == Service.vsegpt,
          );
        }
        final badPayload = api.check(service, key);
        transport.pending.last.complete({'status': 'ok', 'data': {}});
        expect(await badPayload, KeyStatus.malformed);
        final policy = api.check(service, key);
        transport.pending.last.completeError(
          const ApiFailure('catalog.error.policy'),
        );
        final restricted = await policy;
        expect(
          restricted.maySaveUnverified(service),
          service == Service.vsegpt,
        );
        expect(
          restricted,
          service == Service.vsegpt
              ? KeyStatus.unverified
              : KeyStatus.restricted,
        );
      }
    },
  );
  test('wrong provider and empty suffix never invoke a transport', () async {
    final transport = DelayedProvider(), api = ProviderApi(transport);
    for (final key in [
      'sk-or-vis-test-only',
      'sk-or-vis',
      'sk-or-unknown',
      'sk-or-v1-',
    ]) {
      expect(await api.check(Service.openrouter, key), KeyStatus.invalid);
    }
    expect(transport.pending, isEmpty);
  });
}
