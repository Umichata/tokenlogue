import 'dart:convert';

import 'package:cryptography/cryptography.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:tokenlogue_dart/data/providers.dart';
import 'package:tokenlogue_dart/data/transport.dart';
import 'package:tokenlogue_dart/data/vault.dart';
import 'package:tokenlogue_dart/domain/provider.dart';
import 'package:tokenlogue_dart/presentation/controls.dart';
import 'package:tokenlogue_dart/presentation/provider_page.dart';
import 'package:tokenlogue_dart/presentation/theme.dart';

class _Replies implements Transport {
  _Replies(this.provider);
  final Service provider;
  final responses = <Resource, Payload>{};
  final failures = <Resource, String>{};

  @override
  Future<Payload> request(
    Service service,
    String key,
    Resource resource, [
    Payload? body,
  ]) async {
    expect(service, provider);
    expect(Service.detect(key), service);
    expect(body, isNull);
    expect(resource, anyOf(Resource.key, Resource.balance));
    if (failures[resource] case final error?) throw ApiFailure(error);
    return responses[resource]!;
  }
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  for (final language in ['en', 'ru']) {
    for (final service in Service.values) {
      testWidgets(
        '$language: provider card shows independent account, key and quota results for ${service.label}',
        (tester) async {
          final words =
              jsonDecode(
                    await rootBundle.loadString(
                      'assets/locales/$language.json',
                    ),
                  )
                  as Map;
          String t(String k) => words[k] as String;
          final replies = _Replies(service);
          final api = ProviderApi(replies);
          final profile = UnlockedProfile(
            'display-test',
            SecretKey(List.filled(32, 7)),
            {
              service.name: {
                'key': service == Service.openrouter
                    ? 'sk-or-v1-display-test'
                    : 'sk-or-vis-display-test',
                'verified': service == Service.openrouter,
              },
            },
          );
          final accounts = AccountState(profile, api);
          await tester.pumpWidget(
            MaterialApp(
              theme: buildTheme(),
              home: Scaffold(
                body: ListenableBuilder(
                  listenable: accounts,
                  builder: (_, _) => ProviderPage(
                    initial: service,
                    t: t,
                    vault: ProfileVault(),
                    profile: profile,
                    api: api,
                    accounts: accounts,
                    policy: 'manual',
                    setPolicy: (_) async {},
                    onKeyChanged: (_) {},
                  ),
                ),
              ),
            ),
          );
          final refresh = find.text(t('providers.refresh_balance'));
          Future<void> update() async {
            await tester.ensureVisible(refresh);
            await tester.pumpAndSettle();
            await tester.tap(refresh);
            await tester.pumpAndSettle();
          }

          String balance(String amount) => interpolate(t('providers.balance'), {
            'provider': service.label,
            'amount': amount,
            'currency': service.currency,
          });
          if (service == Service.vsegpt) {
            for (final (subscription, user, credits, expected) in [
              ('ok', 0, '1.2', 'ready'),
              ('ok', 1, '1.2', 'warning'),
              ('expired', 0, '1.2', 'subscription_required'),
              ('ok', 2, '0', 'insufficient_funds'),
              ('ok', 2, '3', 'account_disabled'),
            ]) {
              replies.responses[Resource.balance] = {
                'status': 'ok',
                'data': {
                  'credits': credits,
                  'user_status': user,
                  'subscription_status': subscription,
                },
              };
              await update();
              expect(find.text(balance(credits)), findsOneWidget);
              final authorizationLabel = switch (expected) {
                'subscription_required' ||
                'warning' => 'providers.status.$expected',
                _ => 'providers.status.connected',
              };
              expect(find.text(t(authorizationLabel)), findsOneWidget);
              if (expected != 'ready') {
                expect(
                  find.text(t('providers.balance_status.$expected')),
                  findsOneWidget,
                );
              }
            }
            for (final (failure, label) in [
              ('catalog.error.auth', 'providers.balance_status.invalid'),
              (
                'catalog.error.policy',
                'providers.balance_status.restricted.vsegpt',
              ),
              ('catalog.error.rate', 'service.auth_rate'),
              ('catalog.error.schema', 'service.response_format'),
              ('catalog.error.tls', 'service.auth_tls'),
              ('catalog.error.timeout', 'service.auth_timeout'),
              (
                'catalog.error.network',
                'providers.balance_status.network_error',
              ),
            ]) {
              replies.failures[Resource.balance] = failure;
              await update();
              expect(find.text(t(label)), findsOneWidget);
              final status = failure == 'catalog.error.auth'
                  ? 'providers.status.invalid'
                  : 'providers.status.unverified';
              expect(find.text(t(status)), findsOneWidget);
              expect(find.text(t('providers.status.connected')), findsNothing);

              expect(
                find.text(t('providers.balance_status.stale')),
                findsOneWidget,
              );
              expect(find.text(balance('3')), findsOneWidget);
            }
          } else {
            replies.responses[Resource.key] = {
              'data': {
                'limit_remaining': '4.5',
                'free_model_daily_requests': {
                  'used': 2,
                  'limit': 10,
                  'remaining': 8,
                },
              },
            };
            replies.failures[Resource.balance] = 'catalog.error.policy';
            await update();
            final quota = interpolate(t('providers.daily_free_quota'), {
              'remaining': 8,
              'limit': 10,
            });
            expect(find.text(quota), findsOneWidget);
            expect(
              find.text(
                interpolate(t('providers.key_remaining'), {
                  'amount': '4.5',
                  'currency': 'USD',
                }),
              ),
              findsOneWidget,
            );
            expect(
              find.text(t('providers.balance_status.restricted.openrouter')),
              findsOneWidget,
            );
            expect(
              find.text(
                interpolate(t('providers.balance_unavailable'), {
                  'provider': 'OpenRouter',
                }),
              ),
              findsOneWidget,
            );
            replies.failures.clear();
            replies.responses[Resource.balance] = {
              'data': {'total_credits': '5', 'total_usage': '1.8'},
            };
            replies.responses[Resource.key] = {
              'data': {
                'limit_remaining': null,
                'free_model_daily_requests': {
                  'used': 2,
                  'limit': 10,
                  'remaining': 9,
                },
              },
            };
            await update();
            expect(find.text(balance('3.2')), findsOneWidget);
            expect(find.text(quota), findsNothing);
            expect(find.text(t('providers.key_limit_not_set')), findsOneWidget);
            replies.failures[Resource.key] = 'catalog.error.auth';
            await update();
            expect(find.text(t('providers.status.invalid')), findsOneWidget);
            expect(find.text(balance('3.2')), findsOneWidget);
            expect(find.text(t('providers.status.connected')), findsNothing);
          }
          await tester.pumpWidget(const SizedBox.shrink());
          accounts.dispose();
          profile.dispose();
        },
      );
    }
  }
}
